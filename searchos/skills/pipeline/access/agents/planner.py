"""站点规划：探索、开发计划和需求修订。"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from searchos.skills.pipeline.access.agents.prompts.planner import ADVICE_PROMPT, PLAN_PROMPT
from searchos.skills.pipeline.access.artifacts import ToolResultStore
from searchos.skills.pipeline.access.session import (
    budget_signal,
    final_instruction,
    prepare_messages_async,
    tool_protocol_error,
)
from searchos.skills.pipeline.access.tools.execute import PLANNER_EXEC_TOOL as EXEC_TOOL
from searchos.skills.pipeline.access.tools.execute import execute_research as execute
from searchos.skills.pipeline.access.tools.web import RESEARCH_TOOLS
from searchos.util.json_extract import extract_json_object


def usable_observation(observation):
    """兼容旧研究记录；读取错误使观察失效。"""
    result = observation.get('result') or {}
    content = str(result.get('content', ''))
    usable = bool(observation.get('usable', not result.get('error'))) and not (
        result.get('error') or '[FETCH_ERROR]' in content or '[TOOL_ERROR]' in content
        or '[NOTE] Live fetch failed;' in content
        or result.get('content_source') in {'none', 'search_fallback'})
    if observation.get('tool') == 'exec':
        return usable and bool(
            result.get('status') == 'completed' and result.get('exit_code') == 0
            and result.get('started') is True and result.get('execution_id')
            and not result.get('timed_out') and not result.get('truncated')
            and ((isinstance(result.get('stdout'), str) and result['stdout'].strip())
                 or result.get('artifacts'))
            and not any(stream.get('log_truncated') for stream in result.get('streams', {}).values())
        )
    return usable


def page_observation_ids(observations):
    """仅页面读取属于网页证据；代码输出与保存结果页各自保留来源类别。"""
    return {o['id'] for o in observations if usable_observation(o)
            and o.get('tool') in {'open', 'find', 'web_open', 'web_find'}
            and o.get('result', {}).get('live_evidence') is not False
            and o.get('result', {}).get('content_source') not in {'search_results', 'search_cache', 'execution', 'artifact'}}


def research_observation_ids(observations):
    """计划引用页面读取或成功执行；独立验收核对来源与业务语义。"""
    return page_observation_ids(observations) | {
        o['id'] for o in observations if o.get('tool') == 'exec' and usable_observation(o)
    }


def research_observation_index(observations):
    """提供原始研究 ID 与短摘要；全文继续由观察和历史文件保存。"""
    eligible = research_observation_ids(observations)
    index = []
    for observation in observations:
        if observation['id'] not in eligible:
            continue
        result, args = observation.get('result') or {}, observation.get('args') or {}
        text = result.get('title') or (result.get('stdout') if observation.get('tool') == 'exec' else result.get('content')) or ''
        item = {'id': observation['id'], 'tool': observation.get('tool'),
                'summary': re.sub(r'\s+', ' ', str(text)[:1000]).strip()[:120]}
        source = result.get('source_url') or result.get('url') or args.get('id_or_url')
        if isinstance(source, str) and source.startswith(('http://', 'https://')):
            item['source'] = source[:160]
        index.append(item)
    return index


def parse_object(message):
    text = message.content
    if isinstance(text, list):
        text = ''.join(p if isinstance(p, str) else p.get('text', '')
                       for p in text if isinstance(p, (str, dict)))
    text = str(text).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = extract_json_object(text, unique=True)
        if value is None:
            raise ValueError('LLM response must contain a complete JSON object') from None
    if not isinstance(value, dict):
        raise ValueError('LLM response must be a JSON object')
    return value


def validate_plan(value, observations):
    """只检查契约自洽和证据引用；来源真实性由包外验收判断。"""
    if not isinstance(value, dict):
        raise ValueError('missing site capability plan')
    caps = deepcopy(value.get('capabilities'))
    if not isinstance(caps, list) or not caps:
        raise ValueError('plan requires a nonempty capabilities list')
    ids = set()
    known = {o['id'] for o in observations if usable_observation(o)}
    research = research_observation_ids(observations)
    observed = {observation['id']: observation for observation in observations}
    def artifact_hint(refs):
        artifacts = [ref for ref in refs if isinstance(ref, str)
                     and observed.get(ref, {}).get('result', {}).get('content_source') == 'artifact'] if isinstance(refs, list) else []
        return (' Cited artifact/history read IDs: ' + ', '.join(artifacts)
                + '. Cite the original research observation IDs inside that content; '
                'see research_observations for eligible original IDs.') if artifacts else ''
    for cap in caps:
        if not isinstance(cap, dict):
            raise ValueError('capability must be an object')
        name = cap.get('id', '')
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', name) or name in ids:
            raise ValueError('capability IDs must be unique lowercase names')
        ids.add(name)
        if not isinstance(cap.get('purpose'), str) or not cap['purpose'].strip():
            raise ValueError('capability purpose is required')
        acceptance = cap.get('acceptance', [])
        if not isinstance(acceptance, list) or any(not isinstance(item, str) or not item.strip() for item in acceptance):
            raise ValueError(f'{name}.acceptance must contain business outcomes')
        if 'implementation' in cap and not isinstance(cap['implementation'], str):
            raise ValueError(f'{name}.implementation must be research notes')
        # 实际接口由 Builder 声明；研究样本保留在 implementation 和原始观察中。
        for key in set(cap) - {'id', 'purpose', 'acceptance', 'implementation', 'evidence_ids', 'depends_on'}:
            cap.pop(key)
        refs = cap.get('evidence_ids')
        if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref in known for ref in refs):
            raise ValueError(f'{name}.evidence_ids must cite usable observed research evidence' + artifact_hint(refs))
        if not research.intersection(refs):
            raise ValueError(f'{name}.evidence_ids must include a successfully read page or successful research execution; search snippets alone cannot lock a capability' + artifact_hint(refs))
        dependencies = cap.setdefault('depends_on', [])
        if not isinstance(dependencies, list) or not all(isinstance(d, str) for d in dependencies):
            raise ValueError('depends_on must contain capability IDs')
    graph = {c['id']: c['depends_on'] for c in caps}
    def visit(name, path):
        if name not in ids or name in path:
            raise ValueError('unknown or cyclic capability dependency')
        for dependency in graph[name]:
            visit(dependency, path | {name})
    for name in ids:
        visit(name, set())
    limitations = value.get('limitations', [])
    if not isinstance(limitations, list) or not all(isinstance(s, str) for s in limitations):
        raise ValueError('limitations must be strings')
    return deepcopy({'capabilities': caps, 'limitations': limitations})


class SitePlannerAgent:
    def __init__(self, model, workspace, record, *, max_turns=50):
        if type(max_turns) is not int or max_turns < 1:
            raise ValueError('planner max_turns must be a positive integer')
        self.model, self.workspace, self.record = model, workspace, record
        self.max_turns = max_turns
        self.result_store = getattr(getattr(workspace, 'package', None), 'result_store', None) or ToolResultStore(
            record.root / 'tool-results', clean=getattr(record, 'clean', None))
        from searchos.skills.pipeline.access import CONTRACT_VERSION
        self.state = {'version': CONTRACT_VERSION, 'plan': None, 'observations': [], 'dialogues': [], 'calls': 0}
        self.path = record.root / 'site-session.json'

    def save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.record.clean(self.state), ensure_ascii=False, indent=2))
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def observe(self, tool, args, result, actor):
        if tool not in {'search', 'open', 'find', 'web_search', 'web_open', 'web_find',
                        'read_file', 'exec', 'send_message', 'submit_for_validation'}:
            return None
        oid = f"obs-{len(self.state['observations']) + 1}"
        item = {'id': oid, 'actor': actor, 'tool': tool, 'args': self.record.clean(args),
                'result': self.record.clean(result), 'usable': not bool(result.get('error'))}
        item['usable'] = usable_observation(item)
        self.state['observations'].append(item)
        self.save()
        return oid

    async def dispatch(self, name, args):
        if name == 'exec':
            return await execute(self.workspace, **args)
        if name not in {'search', 'open', 'find'}:
            raise ValueError('planner tools are limited to search, find, open and exec')
        args = dict(args)
        if name == 'open':
            target = str(args['id_or_url'])
            if not target.isdigit() and not target.startswith(('https://', 'http://')):
                path = Path(target)
                if '..' in path.parts:
                    raise ValueError('open path must not contain parent traversal')
                if not path.is_absolute():
                    artifact = self.workspace.runtime_dir / 'planner' / 'work' / path
                    if artifact.is_file():
                        target = str(artifact)
                result = await self.workspace.package.read_file(
                    path=target, offset=args.get('offset', 0), limit=args.get('limit', 16000))
                return {**result, 'content_source': 'artifact', 'live_evidence': False}
            args = {key: value for key, value in args.items() if key in {'id_or_url', 'loc'}}
        return await self.workspace.browser.dispatch('web_' + name, args)

    async def converse(self, messages, turns, validator=None, *, response_validator=None):
        """执行有界研究循环，最终 JSON 经角色契约校验后返回。"""
        planning = validator is not None
        last_error = ''
        contract_error = ''
        if planning:
            self.state.pop('failure', None)
        research_turns = max(1, turns - 2)
        # 工具目录保持稳定；整理阶段由执行层拒绝研究调用并回传纠正信息。
        model = self.model.bind_tools([*RESEARCH_TOOLS, EXEC_TOOL])
        for turn in range(turns + 1):
            finalizing = turn >= research_turns
            if finalizing:
                directory = self.result_store.present(research_observation_index(self.state['observations']))
                messages.append(HumanMessage(content='研究观察目录：\n' + json.dumps(directory, ensure_ascii=False)))
            messages = await prepare_messages_async(messages, self.workspace, role='planner', model=self.model)
            instruction = (f'整理调用 {turn - research_turns + 1}/{turns + 1 - research_turns}。'
                    + final_instruction('planner')
                    + '引用研究观察目录中的原始研究 ID；读取历史文件时沿用内容中的原 ID。'
                    if finalizing else '依据已有观察推进计划或需求澄清，根据剩余轮数安排探索和最终 JSON 整理。')
            if last_error:
                instruction += '\n最近校验反馈：' + last_error[:1000]
            signal = budget_signal('planner', call=turn + 1, call_limit=turns + 1,
                phase='finalization' if finalizing else 'research',
                phase_limit=turns + 1 if finalizing else research_turns)
            self.state['budget'] = signal
            messages.append(HumanMessage(content=instruction + '\n剩余次数包含本次调用。运行预算：\n'
                + json.dumps(signal, ensure_ascii=False)))
            self.state['calls'] += 1
            self.save()
            try:
                answer = await model.ainvoke(messages)
            except Exception as exc:
                if not finalizing or not tool_protocol_error(exc):
                    raise
                last_error = str(exc)
                self.validation_error(exc, kind='tool_protocol')
                self.record.event('agent_tool_protocol_rejected', role='planner', call=self.state['calls'],
                                  error=self.record.clean(str(exc)))
                messages.append(HumanMessage(content='网关拒绝了工具调用。' + final_instruction('planner')))
                continue
            self.record.event('site_intent_response', content=answer.content, tool_calls=answer.tool_calls,
                              usage=getattr(answer, 'usage_metadata', None))
            messages.append(answer)
            calls = answer.tool_calls or []
            if not calls:
                parsed = False
                try:
                    value = parse_object(answer)
                    parsed = True
                    if response_validator is not None:
                        return response_validator(value)
                    return self.accept_proposal(value, validator)
                except (ValueError, TypeError) as exc:
                    last_error = str(exc)
                    if parsed:
                        contract_error = last_error
                    kind = ('plan_validation' if planning else 'advice_validation') if parsed else 'response_format'
                    self.validation_error(exc, kind=kind)
                    messages.append(HumanMessage(content=f'最终 JSON 未通过校验，请修复具体字段：{exc}'))
                    continue
            for call in calls:
                try:
                    if finalizing:
                        raise ValueError('finalization_tool_blocked: ' + final_instruction('planner'))
                    result = await self.dispatch(call['name'], call['args'])
                except Exception as exc:
                    result = {'error': str(exc)}
                oid = self.observe(call['name'], call['args'], result, 'planner')
                shown = {'observation_id': oid, **result}
                shown = (self.result_store.clean(shown) if result.get('content_source') == 'artifact'
                         else self.result_store.present(shown))
                messages.append(ToolMessage(content=json.dumps(shown, ensure_ascii=False),
                                            tool_call_id=call['id']))
        reason = contract_error or last_error
        role = 'site intent' if planning else 'site planner message'
        message = role + ' call budget exhausted without a valid response' + (': ' + reason if reason else '')
        if planning:
            code = 'site_plan_invalid' if research_observation_ids(self.state['observations']) else 'site_page_evidence_unavailable'
            raise self.planning_failure(code, message)
        raise ValueError(message)

    def planning_failure(self, code, message):
        failure = {'code': code, 'message': message, 'call': self.state['calls']}
        self.state['failure'] = failure
        self.save()
        self.record.event('site_intent_failed', **failure)
        return ValueError(f'{message} [{code}]')

    def accept_proposal(self, value, validator):
        if validator is not None:
            previous = self.state.get('last_proposal')
            if previous is not None and previous != value:
                self.state.setdefault('proposal_history', []).append(previous)
            self.state['last_proposal'] = deepcopy(value)
            self.save()
        return validator(value) if validator else value

    def validation_error(self, error, *, kind='plan_validation'):
        self.state.setdefault('validation_errors', []).append({'call': self.state['calls'], 'kind': kind, 'error': str(error)})
        self.save()

    async def prepare(self, host, urls, notes, resume=None, resume_input=None):
        if resume is not None:
            self.state = json.loads(Path(resume).read_text())
            from searchos.skills.pipeline.access import CONTRACT_VERSION
            if self.state.get('version') != CONTRACT_VERSION:
                raise ValueError('旧版站点计划仅供查看，请重新创建任务以使用新的角色契约。')
            if self.state.get('host') != host:
                raise ValueError('site session host does not match request')
            if resume_input:
                replayed = await self.dispatch('exec', resume_input)
                self.observe('exec', resume_input, replayed, 'planner')
            if self.state.get('plan') is not None:
                self.state['plan'] = validate_plan(self.state['plan'], self.state['observations'])
                self.save()
                return self.state['plan']
            self.record.event('site_intent_resumed', mode='unlocked_proposal',
                              starting_calls=self.state['calls'], max_calls=self.max_turns + 1)
        self.state.update(host=host, entry_urls=urls, user_need=notes)
        context = {'host': host, 'entry_urls': urls, 'user_need': notes}
        if resume is not None:
            context.update(previous_proposal=self.state.get('last_proposal'),
                           observations=self.state['observations'])
        messages = [SystemMessage(content=PLAN_PROMPT),
                    HumanMessage(content=json.dumps(self.result_store.present(context), ensure_ascii=False))]
        for url in urls[:2]:
            try:
                result = await self.dispatch('open', {'id_or_url': url})
            except Exception as exc:
                result = {'error': str(exc)}
            oid = self.observe('open', {'id_or_url': url}, result, 'planner')
            messages.append(HumanMessage(content=json.dumps(
                self.result_store.present({'observation_id': oid, **result}), ensure_ascii=False)))
        self.state['plan'] = await self.converse(messages, self.max_turns,
            validator=lambda value: validate_plan(value, self.state['observations']))
        self.state.setdefault('plan_version', 1)
        self.save()
        return self.state['plan']

    def validate_reply(self, value):
        if (value.get('status') not in {'clarified', 'blocked', 'needs_evidence'}
                or not isinstance(value.get('guidance'), str) or not value['guidance'].strip()):
            raise ValueError('planner reply requires status and nonempty guidance')
        refs = value.get('evidence_ids', [])
        known = {o['id'] for o in self.state['observations']}
        if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in known for ref in refs):
            raise ValueError('planner reply evidence_ids must cite observed research')
        reply = {'status': value['status'], 'guidance': value['guidance'], 'evidence_ids': refs}
        if value.get('plan') is not None:
            if value['status'] != 'clarified':
                raise ValueError('a revised plan requires clarified status')
            reply['plan'] = validate_plan(value['plan'], self.state['observations'])
        return reply

    async def receive_message(self, content):
        """响应宿主交付的角色消息；宿主同步计划对应的验收状态。"""
        if not isinstance(content, (str, dict)) or not content:
            raise ValueError('planner message must be nonempty text or an object')
        item = {'content': deepcopy(content)}
        self.state['dialogues'].append(item)
        self.save()
        context = {'message': content, 'plan': self.state['plan'],
                   'observations': self.result_store.present(self.state['observations'])}
        try:
            reply = await self.converse([
                SystemMessage(content=ADVICE_PROMPT),
                HumanMessage(content=json.dumps(context, ensure_ascii=False))],
                self.max_turns, response_validator=self.validate_reply)
            revised = reply.get('plan')
            if revised is not None and revised != self.state['plan']:
                previous = deepcopy(self.state['plan'])
                self.state.setdefault('initial_plan', previous)
                version = self.state.get('plan_version', 1) + 1
                self.state.setdefault('revisions', []).append({
                    'version': version, 'previous_plan': previous,
                    'evidence_ids': reply['evidence_ids'], 'guidance': reply['guidance']})
                self.state.update(plan=revised, plan_version=version)
                reply['contract_revision'] = version - 1
            item['answer'] = deepcopy(reply)
            self.save()
            return reply
        except Exception as exc:
            item['error'] = str(exc)
            self.save()
            raise

    def builder_notes(self):
        plan = self.state['plan']
        refs = {ref for cap in plan['capabilities'] for ref in cap['evidence_ids']}
        evidence = [o for o in self.state['observations'] if o['id'] in refs]
        return ('\n## 站点开发计划\n在一个技能包内实现计划中的能力，按任务选择实现与验证方式。'
                '\nBuilder 自主设计 CLI、参数、字段与 JSON 结构，并向 Validator 提交实际执行声明。--help 离线成功。'
                '\n无匹配或非法输入可返回空结果或明确失败，建议附状态与诊断；错误标签及退出码形式差异只作提示。'
                '边界观察按需进行，验收检查声明范围内正常输入的可用性、参数效果、数据真实性和来源。'
                + '\n能力计划：\n' + json.dumps(plan, ensure_ascii=False)
                + '\n## 研究观察\n' + json.dumps(self.result_store.present({'observations': evidence}), ensure_ascii=False))
