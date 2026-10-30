"""技能开发：实现、自测、交验及失败修复。"""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from searchos.skills.pipeline.access.agents.prompts.builder import SYSTEM_PROMPT, user_prompt
from searchos.skills.pipeline.access.session import (
    FINALIZATION_ATTEMPTS,
    MAX_REPAIR_TURNS,
    budget_signal,
    final_instruction,
    prepare_messages_async,
    tool_protocol_error,
    validate_repair_budget,
)
from searchos.skills.pipeline.access.tools.execute import BUILDER_EXEC_TOOL
from searchos.skills.pipeline.access.tools.files import (
    EDIT_FILE_TOOL,
    READ_FILE_TOOL,
    WRITE_FILE_TOOL,
    _tool,
)
from searchos.skills.pipeline.access.tools.web import TOOL_DEFINITIONS as BROWSER_TOOLS

SEND_MESSAGE_TOOL = _tool('send_message', '向 validator 提交当前候选；调用方式、参数和输出说明写入 SKILL.md，Validator 自主阅读并验收。'
    '向 planner 澄清业务范围或研究依据。宿主保存消息并顺序执行接收角色。', {
    'role': {'type': 'string', 'enum': ['planner', 'builder', 'validator']},
    'content': {'oneOf': [{'type': 'string'}, {'type': 'object'}]},
}, ['role', 'content'])

TOOL_DEFINITIONS = [*BROWSER_TOOLS, BUILDER_EXEC_TOOL, READ_FILE_TOOL,
                    WRITE_FILE_TOOL, EDIT_FILE_TOOL, SEND_MESSAGE_TOOL]

class AccessBuilderAgent:
    def __init__(self, workspace, final_dir, host, probe_urls, notes, tool_model,
                 max_turns, diagnostics, record, *, context_model=None):
        self.workspace, self.final_dir = workspace, final_dir
        self.host, self.probe_urls, self.notes = host, probe_urls, notes
        self.model, self.max_turns = tool_model, max_turns
        self.context_model = context_model if context_model is not None else tool_model
        self.diagnostics, self.record = diagnostics, record
        self.messages = []

    async def run(self):
        workspace, record, diagnostics = self.workspace, self.record, self.diagnostics
        self.messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(
            content=user_prompt(self.host, self.probe_urls, self.notes)
                + '\nFinal package name: ' + self.final_dir.name)]
        if workspace.validation.examples:
            self.messages.append(HumanMessage(content='验收目标与建议调用样例：\n'
                + json.dumps(workspace.validation.examples, ensure_ascii=False)))
        turn = -1
        call_limit = self.max_turns + FINALIZATION_ATTEMPTS
        maximum_calls = self.max_turns + FINALIZATION_ATTEMPTS + MAX_REPAIR_TURNS * workspace.validation.max_repair_attempts
        budgeted_round = workspace.validation.validation_rounds
        repair_budget, budget_source, phase_start = None, None, 0
        while True:
            current = workspace.validation.current_validation_report()
            if (workspace.validation.validation_rounds and workspace.validation.package_preflight()['preflight_valid']
                    and current.get('next_actions')
                    and all(item['action'] == 'wait_external' for item in current['next_actions'])):
                diagnostics['exit_reason'] = 'wait_external'
                break
            if budgeted_round < workspace.validation.validation_rounds < workspace.validation.max_repair_attempts + 1:
                failed_report = workspace.validation.last_validation
                try:
                    repair_budget = validate_repair_budget(failed_report.get('repair_budget'))
                    budget_source = 'validator'
                except ValueError:
                    repair_budget = {'max_turns': MAX_REPAIR_TURNS,
                        'reason': '本轮未取得 Validator 修复预算，使用后备修复额度。'}
                    budget_source = 'fallback'
                previous_limit, phase_start = call_limit, turn + 1
                call_limit = min(maximum_calls, phase_start + repair_budget['max_turns'])
                budgeted_round = workspace.validation.validation_rounds
                record.event('builder_repair_continued', turn=turn + 1,
                    previous_limit=previous_limit, call_limit=call_limit,
                    validation_rounds=budgeted_round, repair_budget=repair_budget,
                    budget_source=budget_source)
            if turn + 1 >= call_limit:
                report = workspace.validation.current_validation_report()
                unfinished = (report.get('stage') == 'pending' or not report.get('report_complete', True)
                              or any(item.get('status') == 'incomplete'
                                     for item in report.get('capability_results', {}).values()))
                if (workspace.package.files and workspace.validation.package_preflight()['preflight_valid'] and unfinished
                        and workspace.validation.validation_rounds < workspace.validation.max_repair_attempts + 1):
                    record.event('validation_handoff_fallback', reason='max_turns',
                                 candidate_version=workspace.validation.validation_fingerprint())
                    fallback = await workspace.send_message('validator', {'request': 'validate'})
                    self.messages.append(HumanMessage(content='自动交验结果，按反馈继续修复：\n'
                        + json.dumps(workspace.package.result_store.present(fallback), ensure_ascii=False)))
                    diagnostics['final_validation_handoff'] = True
                    if workspace.validation.validation_passed:
                        diagnostics['exit_reason'] = 'validation_passed'
                        break
                    if workspace.validation.validation_rounds >= workspace.validation.max_repair_attempts + 1:
                        diagnostics['exit_reason'] = 'validation_round_limit'
                        break
                if budgeted_round < workspace.validation.validation_rounds < workspace.validation.max_repair_attempts + 1:
                    continue
                break
            turn += 1
            closing = repair_budget is not None or turn >= self.max_turns
            pending = workspace.validation.current_validation_report()
            preflight = workspace.validation.package_preflight()
            self.messages = await prepare_messages_async(
                self.messages, workspace, role='builder', model=self.context_model)
            if not preflight['preflight_valid']:
                self.messages.append(HumanMessage(content='静态预检与补齐项：\n'
                    + json.dumps(workspace.package.result_store.present(preflight), ensure_ascii=False)))
            actions = preflight['next_actions'] if not preflight['preflight_valid'] else pending.get('next_actions')
            if actions and (workspace.validation.validation_rounds or call_limit - turn <= 5):
                self.messages.append(HumanMessage(content='当前包与修复定位：按函数 read_file 参数读取，保留已有实现并局部修改。\n'
                    + json.dumps(workspace.package.result_store.present({
                        'package_files': pending['package_files'], 'next_actions': actions,
                        'function_index_file': pending['function_index_file']}), ensure_ascii=False)))
            instruction = (
                f'修复调用 {turn - phase_start + 1}/{call_limit - phase_start}。' + final_instruction('builder')
                if repair_budget is not None else
                f'收尾调用 {turn - self.max_turns + 1}/{call_limit - self.max_turns}。' + final_instruction('builder')
                if closing else f'开发调用 {turn + 1}/{self.max_turns}，独立验收已执行 {workspace.validation.validation_rounds} 轮。')
            signal = budget_signal('builder', call=turn + 1, call_limit=call_limit,
                phase='repair' if repair_budget is not None else 'finalization' if closing else 'development',
                phase_limit=call_limit if closing else self.max_turns, total_limit=maximum_calls)
            signal.update(validation_rounds=workspace.validation.validation_rounds,
                          remaining_validations=workspace.validation.max_repair_attempts + 1 - workspace.validation.validation_rounds)
            if repair_budget is not None:
                signal.update(repair_budget=repair_budget, budget_source=budget_source)
            workspace.builder_budget = signal
            diagnostics['budget'] = signal
            self.messages.append(HumanMessage(content=instruction + '\n剩余次数包含本次调用。运行预算：\n'
                + json.dumps(signal, ensure_ascii=False)))
            diagnostics['turns_attempted'] = turn + 1
            diagnostics.update(call_limit=call_limit, maximum_calls=maximum_calls)
            record.event('model_started', turn=turn + 1, closing=closing, phase='build', budget=signal)
            try:
                response = await self.model.ainvoke(self.messages)
            except Exception as exc:
                if closing and tool_protocol_error(exc):
                    diagnostics['exit_reason'] = 'max_turns'
                    record.event('agent_tool_protocol_rejected', role='builder', turn=turn + 1,
                                 error=record.clean(str(exc)))
                    self.messages.append(HumanMessage(content='网关拒绝了工具调用。' + final_instruction('builder')))
                    continue
                diagnostics.update(exit_reason='model_error', model_error_type=type(exc).__name__,
                                   model_error=record.clean(str(exc)))
                record.event('model_error', error_type=type(exc).__name__)
                break
            diagnostics['turns_completed'] = turn + 1
            for key, value in (getattr(response, 'usage_metadata', None) or {}).items():
                if key in {'input_tokens', 'output_tokens', 'total_tokens'} and isinstance(value, int):
                    diagnostics['model_usage'][key] = diagnostics['model_usage'].get(key, 0) + value
            calls = getattr(response, 'tool_calls', None) or []
            self.messages.append(response)
            record.event('model_completed', turn=turn + 1, content=response.content,
                         tool_calls=calls, usage=getattr(response, 'usage_metadata', None))
            for call in calls:
                result = await run_tool(workspace, call)
                self.messages.append(result)
                record.event('tool_result', turn=turn + 1, name=call.get('name'),
                             call_id=call.get('id'), content=result.content)
            if workspace.validation.validation_passed:
                diagnostics['exit_reason'] = 'validation_passed'
                break
            report = workspace.validation.current_validation_report()
            if not calls:
                if workspace.package.files and report.get('next_actions'):
                    self.messages.append(HumanMessage(content='当前候选尚待交接或修复。当前版本尚未完成修复或独立验收。'
                        '请执行待办并通过 send_message(role="validator") 交验：\n'
                        + json.dumps(report['next_actions'], ensure_ascii=False)))
                else:
                    diagnostics['exit_reason'] = 'builder_finished'
                    break
            if workspace.validation.validation_rounds >= workspace.validation.max_repair_attempts + 1:
                diagnostics['exit_reason'] = 'validation_round_limit'
                break
            if closing:
                diagnostics['exit_reason'] = 'max_turns'
        record.event('generation_stopped', reason=diagnostics['exit_reason'],
                     validation_rounds=workspace.validation.validation_rounds)
        record.summary(diagnostics)


async def run_tool(workspace, tool_call):
    """Execute one normalized LangChain tool call and return a ToolMessage."""
    from langchain_core.messages import ToolMessage

    name = ""
    call_id = ""
    args = {}
    try:
        if not isinstance(tool_call, dict):
            raise TypeError("tool call must be a normalized mapping")
        name = str(tool_call.get("name", ""))
        call_id = str(tool_call.get("id", ""))
        args = tool_call.get("args") or {}
        if isinstance(args, str):
            args = json.loads(args or "{}")
        if not isinstance(args, dict):
            raise TypeError("tool call args must be an object")
        result = await workspace.dispatch(name, args)
        if (name in {'read_file', 'edit_file', 'write_file', 'exec'} and isinstance(result, dict)
                and (result.get('error') or result.get('exit_code') not in (None, 0))):
            result = {**result, 'recovery': workspace.file_recovery(args.get('path', ''))}
        if workspace.site_intent is not None and name != 'send_message':
            observation = workspace.site_intent.observe(name, args, result, 'builder')
            if observation is not None:
                result = {**result, 'observation_id': observation}
        if name != 'read_file' or result.get('error'):
            result = workspace.package.result_store.present(result)
        payload = json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        result = {'error': str(exc)}
        if name in {'read_file', 'edit_file', 'write_file', 'exec'} and isinstance(args, dict):
            result['recovery'] = workspace.file_recovery(args.get('path', ''))
        payload = json.dumps(workspace.package.result_store.present(result), ensure_ascii=False)
    return ToolMessage(
        content=payload,
        tool_call_id=call_id or "missing-tool-call-id",
        name=name or None,
    )
