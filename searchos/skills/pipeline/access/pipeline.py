"""Access Pipeline：规划、开发、交验、修复、草稿恢复和交付。"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from searchos.network import network_scoped
from searchos.skills.core.capabilities import annotate_package
from searchos.skills.intent.models import name_for_host
from searchos.skills.packaging import publish_package
from searchos.skills.pipeline.access import CONTRACT_VERSION
from searchos.skills.pipeline.access.agents.builder import TOOL_DEFINITIONS
from searchos.skills.pipeline.access.agents.planner import research_observation_index
from searchos.skills.pipeline.access.artifacts import ToolResultStore
from searchos.skills.pipeline.access.tools.execute import ExecutionTools
from searchos.skills.pipeline.access.tools.files import PackageFiles
from searchos.skills.pipeline.access.tools.web import ResearchBrowser
from searchos.skills.pipeline.access.validation.checks import (
    validate_access_preflight,
    validate_access_structure,
)
from searchos.skills.pipeline.access.validation.progress import ValidationProgress


class AccessPipeline:
    """一次构建的角色编排；文件与验收数据分别由 package、validation 管理。"""
    TOOL_DEFINITIONS = TOOL_DEFINITIONS

    def __init__(self, output_dir, expected_name=None):
        self._runtime = tempfile.TemporaryDirectory(prefix='searchos-builder-runtime-')
        self.runtime_dir = Path(self._runtime.name)
        self.checkpoint = lambda: None
        self.package = PackageFiles(output_dir, expected_name=expected_name, runtime_dir=self.runtime_dir,
            result_store=ToolResultStore(self.runtime_dir / 'tool-results'), on_change=lambda: self.checkpoint())
        self.validation = ValidationProgress(self.package, plan=self.current_plan, checkpoint=lambda: self.checkpoint())
        self.executor = ExecutionTools(self.package, candidate_version=self.validation.validation_fingerprint)
        self.browser = ResearchBrowser()
        self.site_intent = self.validation_agent = None
        self.builder_budget = {}

    def current_plan(self):
        return self.site_intent.state.get('plan') if self.site_intent is not None else None

    def context_snapshot(self, role):
        checkpoint = dict(candidate_version=self.validation.validation_fingerprint(), validation_rounds=self.validation.validation_rounds,
            capabilities=self.validation.capability_ids, package_files=sorted(self.package.files), plan=self.current_plan(),
            suggested_examples=self.validation.examples, latest_validation=self.package.result_store.present(self.validation.current_validation_report()))
        if role == 'planner' and self.site_intent is not None:
            checkpoint['research_observations'] = research_observation_index(self.site_intent.state.get('observations', []))
        if role == 'validator' and self.validation_agent is not None:
            progress = self.validation_agent.progress()
            if progress:
                checkpoint['validation_progress'] = progress
        return checkpoint

    def close(self):
        self._runtime.cleanup()


    @property
    def record(self):
        return self.validation.record

    @record.setter
    def record(self, value):
        self.validation.record = value


    def file_recovery(self, path=''):
        """返回当前包的权威目录和可执行读取参数，供工具失败后恢复定位。"""
        files = sorted(self.package.files)
        matches = [relative for relative in files if str(path).endswith('/' + relative) or str(path) == relative]
        recovery = {'package_files': files,
                'read_file': {'path': matches[0] if len(matches) == 1 else 'SKILL.md'},
                'instruction': """包文件使用上述相对路径；先读取再局部 edit_file。读取失败后按目录重新定位，保留已有文件。exec(code) 通过 Python Path 变量 SKILL_DIR 只读访问候选；修改使用 edit_file/write_file。函数 read_file 参数中的 offset/limit 按字符计数，沿 next_offset 读至 end_offset。"""}
        try:
            recovery['function_index_file'] = self.validation.function_index()['index_file']
        except (OSError, ValueError) as exc:
            recovery['index_error'] = str(exc)
        return recovery


    async def send_message(self, role, content, *, sender='builder'):
        if role not in {'planner', 'validator'}:
            raise ValueError(f'{sender} cannot dispatch a task to {role}')
        if not isinstance(content, (str, dict)):
            raise ValueError('message content must be text or an object')
        if self.record:
            self.record.event('role_message', sender=sender, role=role, content=content)
        if role == 'planner':
            if self.site_intent is None:
                raise ValueError('this build has no site planner')
            response = await self.site_intent.receive_message(content)
            if response.get('plan') is not None:
                self.checkpoint()
            return response
        if sender != 'builder':
            raise ValueError('only Builder submits candidates for validation')
        report = await self.validate()
        if self.site_intent is not None:
            oid = self.site_intent.observe('send_message', {'role': 'validator'}, report, 'validation')
            if oid is not None:
                report = {**report, 'observation_id': oid}
        return report


    async def validate(self):
        progress = self.validation
        fingerprint = progress.validation_fingerprint()
        previous = progress.last_validation
        same_version = (previous.get('candidate_fingerprint') == fingerprint
                        and previous.get('network_fingerprint') == progress.network_fingerprint)
        incomplete = any(item.get('status') != 'available' for item in previous.get('capability_results', {}).values())
        if (same_version and not previous.get('cancelled') and not previous.get('semantic_error')
                and not incomplete and not previous.get('regression_commands') and previous.get('report_complete', True)):
            return progress.validation_feedback(previous)
        if progress.validation_rounds >= progress.max_repair_attempts + 1:
            return {**progress.current_validation_report(), 'error': 'validation_round_limit'}
        if error := self.package.revision_error():
            return error
        current = progress.begin()
        resume = self.validation_agent.snapshot() if self.validation_agent is not None else None
        if not same_version or previous.get('cancelled'):
            resume = None
        report = gate = None
        with self.package.snapshot() as candidate, self.executor.validation_work(progress.validation_rounds):
            try:
                gate = validate_access_preflight(candidate, self.package.expected_name, self.validation.examples,
                    require_host=self.validation.require_host, expected_host=self.validation.expected_host,
                    capability_ids=progress.capability_ids, require_examples=progress.examples_locked)
                progress.checkpoint_validation_progress({**gate, 'candidate_version': fingerprint, 'report_complete': False})
                if self.record:
                    self.record.event('validation_preflight', version=fingerprint, report=self.package.result_store.present(gate))
                request = progress.prepare_review(gate, resume)
                if self.validation_agent is None or not gate.get('package_valid') or not current.scope['capability_ids']:
                    report = request['deterministic']
                else:
                    report = await self.validation_agent.validate(candidate_dir=candidate, **request)
                report = progress.merge_report(report)
            except BaseException as exc:
                partial = self.validation_agent.snapshot().get('result', {}) if self.validation_agent is not None else {}
                if partial.get('candidate_version') != fingerprint:
                    partial = progress.last_validation if progress.last_validation.get('candidate_version') == fingerprint else {}
                if not partial:
                    partial = {**(gate or {}), 'capability_results': progress.incomplete_results('本轮验收中断，当前版本尚未完成。')}
                partial = deepcopy(partial)
                for item in partial.get('capability_results', {}).values():
                    if item.get('status') == 'available':
                        item.update(status='incomplete', semantic='incomplete', reason='验收已中断，当前版本须重新确认。')
                progress.last_validation = {**progress.merge_report(partial), 'valid': False,
                    'cancelled': isinstance(exc, asyncio.CancelledError), 'report_complete': False,
                    'candidate_version': fingerprint, 'candidate_fingerprint': fingerprint,
                    'validation_rounds': progress.validation_rounds}
                self.checkpoint()
                raise
            finally:
                progress.end()
                if callback := getattr(self.validation_agent, 'on_stage', None):
                    await callback('pipeline')
        if fingerprint != progress.validation_fingerprint():
            report = {**report, 'valid': False, 'error': 'candidate_changed_during_validation',
                'capability_results': progress.incomplete_results('计划或候选文件已改变，请重新提交当前版本。'),
                'current_plan': progress.plan()}
        progress.last_validation = {**report, 'candidate_fingerprint': fingerprint,
                                   'validation_rounds': progress.validation_rounds}
        progress.checked_state = current.contract_state
        self.checkpoint()
        if self.record:
            self.record.event('validation_completed', version=fingerprint, report=self.package.result_store.present(progress.last_validation))
        return progress.validation_feedback(progress.last_validation)

    async def dispatch(self, tool_name, tool_input):
        if tool_name == 'network_check':
            from searchos.skills.pipeline.access.tools.network import check_network
            return await check_network(**tool_input)
        if tool_name in {'search', 'find', 'open'}:
            return await self.browser.dispatch(tool_name, tool_input)
        if tool_name == 'send_message':
            return await self.send_message(**tool_input)
        if tool_name == 'exec':
            return await self.executor.execute(**tool_input)
        if tool_name == 'write_file':
            return await self.package.write_file(**tool_input)
        if tool_name == 'edit_file':
            return await self.package.edit_file(**tool_input)
        if tool_name == 'read_file':
            return await self.package.read_file(**tool_input)
        raise ValueError(f'unknown tool: {tool_name}')


def publication_report(workspace):
    report = workspace.validation.current_validation_report()
    structure = validate_access_structure(workspace.package.output_dir, workspace.package.expected_name,
        require_host=workspace.validation.require_host, expected_host=workspace.validation.expected_host)
    if not structure.get('package_valid'):
        return {**report, **structure, 'valid': False}
    if error := workspace.package.revision_error():
        return {**report, **error}
    results = report.get('capability_results') or workspace.validation.incomplete_results('当前版本尚未完成验收。')
    states = [item['status'] for item in results.values()]
    valid = bool(states) and all(status == 'available' for status in states) and not report.get('cancelled')
    overall = ('passed' if valid else 'partial' if 'available' in states else
               'unavailable' if states and all(status == 'unavailable' for status in states) else 'incomplete')
    return {**report, 'contract_version': CONTRACT_VERSION, 'valid': valid, 'package_valid': True,
            'capability_results': results, 'validation_status': overall}


def save_artifact(workspace, final_dir, diagnostics, record):
    if not workspace.package.files:
        return None
    report = publication_report(workspace)
    destination = record.root / 'artifact' / final_dir.name
    with tempfile.TemporaryDirectory(prefix='.artifact-', dir=record.root) as temporary:
        candidate = Path(temporary) / final_dir.name
        workspace.package.copy_candidate(candidate)
        if report.get('package_valid'):
            annotate_package(candidate, record.clean(report['capability_results']))
        publish_package(candidate, destination)
    receipt = record.clean({**report, 'path': str(destination),
        'status': 'delivered' if report.get('package_valid') else 'draft',
        'stop_reason': diagnostics.get('exit_reason', '')})
    path = record.root / 'artifact.tmp'
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    path.chmod(0o600)
    path.replace(record.root / 'artifact.json')
    diagnostics['artifact_path'] = str(destination)
    record.event('artifact_saved', path=str(destination), package_valid=report.get('package_valid'))
    return destination


def publish_current(workspace, final_dir, diagnostics, record):
    report = publication_report(workspace)
    diagnostics.update(report)
    record.event('final_validation', report=workspace.package.result_store.present(report))
    if not report.get('package_valid'):
        if diagnostics.get('exit_reason') != 'model_error':
            diagnostics['failure_stage'] = 'access_validation'
        return None
    with tempfile.TemporaryDirectory(prefix='.builder-publish-', dir=final_dir.parent) as temporary:
        candidate = Path(temporary) / final_dir.name
        workspace.package.copy_candidate(candidate)
        annotate_package(candidate, record.clean(report['capability_results']))
        publish_package(candidate, final_dir)
    return final_dir


logger = logging.getLogger(__name__)


MAX_TURNS = 50


@network_scoped
async def build_skill(
    host: str,
    probe_urls: list[str],
    *,
    notes: str = "",
    output_dir: Path | None = None,
    builder_model: Any = None,
    model: str | None = None,
    max_turns: int = MAX_TURNS,
    max_repair_attempts: int = 3,
    validation_examples: list[dict] | None = None,
    existing_package: Path | None = None,
    diagnostics: dict | None = None,
    record_dir: Path | None = None,
    resume_draft: Path | None = None,
    site_intent: bool = False,
    intent_model: Any = None,
    planner_max_turns: int = 50,
    validation_model: Any = None,
    validation_max_turns: int = 50,
    site_session_path: Path | None = None,
    on_stage: Any = None,
    allow_interaction: bool = False,
    on_user_action: Any = None,
    revalidate_from: Path | None = None,
    resume_input: dict | None = None,
) -> Path | None:
    """实现并验收 Access 技能，返回附逐能力状态的包目录。

    默认沿用 skill_evolver 的模型、服务端点与执行配置。调用方可分别注入
    builder_model、intent_model 和 validation_model；复用同一模型配置时，
    三个 Agent 仍各自管理会话。model 仅覆盖 CLI 调用的模型名。
    """
    if max_turns < 1:
        raise ValueError('max_turns must be positive')
    if type(max_repair_attempts) is not int or not 1 <= max_repair_attempts <= 3:
        raise ValueError('max_repair_attempts must be an integer from 1 to 3')
    if type(planner_max_turns) is not int or planner_max_turns < 1:
        raise ValueError('planner_max_turns must be a positive integer')
    if validation_max_turns < 1:
        raise ValueError('validation_max_turns must be positive')
    user_need = notes
    from uuid import uuid4

    from searchos.skills.pipeline.access.artifacts import BuildRecord
    final_dir = output_dir or Path("searchos/skills/library/access") / name_for_host(host)
    record = BuildRecord(record_dir or final_dir.parent / '.build-runs' / uuid4().hex)
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update(max_turns=max_turns, planner_max_turns=planner_max_turns,
                       max_repair_attempts=max_repair_attempts,
                       turns_attempted=0, turns_completed=0,
                       exit_reason='running', record_dir=str(record.root))
    diagnostics['example_source'] = 'host' if validation_examples is not None else 'validator'
    diagnostics['model_usage'] = {}
    record.summary(diagnostics)
    if builder_model is None:
        from searchos.config.models import get_model_for

        try:
            builder_model = get_model_for("skill_evolver", model_override=model)
        except Exception as exc:
            diagnostics.update(exit_reason='model_setup_error', model_error_type=type(exc).__name__)
            record.summary(diagnostics)
            raise

    try:
        definitions = list(AccessPipeline.TOOL_DEFINITIONS)
        tool_model = builder_model.bind_tools(definitions)
    except Exception:
        logger.warning(
            "skill_evolver model does not support access-skill builder tools",
            exc_info=True,
        )
        if diagnostics is not None:
            diagnostics.update(stage="model", error="生成模型不支持工具调用", exit_reason="tool_binding_error")
            record.summary(diagnostics)
        return None

    # Build in a hidden sibling staging dir so a half-written skill is never
    # visible to the registry mid-generation; promote it into the library
    # atomically after package validation (same parent => same
    # filesystem => the rename is atomic).
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".staging_{final_dir.name}_", dir=final_dir.parent))
    workspace = AccessPipeline(staging, expected_name=final_dir.name)
    workspace.validation.max_repair_attempts = max_repair_attempts
    from searchos.skills.pipeline.access.artifacts import ToolResultStore
    workspace.package.result_store = ToolResultStore(record.root / 'tool-results', clean=record.clean)
    workspace.validation.expected_host = host
    workspace.record = record
    def checkpoint():
        from searchos.skills.pipeline.drafts import save_draft
        pointer = save_draft(record.root, staging, workspace.package.files, name=final_dir.name,
                             examples=workspace.validation.examples, require_host=workspace.validation.require_host,
                             validation=workspace.validation.last_validation, contract_version=CONTRACT_VERSION)
        if pointer:
            diagnostics['draft_path'] = str(pointer)
    workspace.checkpoint = checkpoint
    from searchos.skills.runtime.browser_session import BrowserSession, current_session
    browser_session = BrowserSession(host, allow_interaction=allow_interaction,
        on_action=on_user_action, checkpoint=checkpoint)
    browser_token = current_session.set(browser_session)
    try:
        if resume_draft is not None:
            from searchos.skills.pipeline.drafts import load_draft
            source, saved = load_draft(resume_draft)
            if saved.get('contract_version') != CONTRACT_VERSION:
                raise ValueError('旧版 Access 草稿仅供查看，请重新创建任务以使用新的角色契约。')
            if saved['name'] != final_dir.name:
                raise ValueError('draft name does not match request')
            for relative in saved['files']:
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, target)
                workspace.package.files.add(relative)
            workspace.validation.examples = saved['examples']
            workspace.validation.examples_locked = bool(saved['examples'])
            workspace.validation.require_host = saved['require_host']
            workspace.validation.last_validation = saved['validation']
            workspace.validation.validation_rounds = int(saved['validation'].get('validation_rounds', 0))
            if existing_package is not None:
                # 恢复更新任务时也要与已安装包比较，不能把旧包通过样例当成修复完成。
                import hashlib

                from searchos.skills.packaging import package_files
                workspace.package.update_base = {
                    relative.as_posix(): hashlib.sha256((existing_package / relative).read_bytes()).hexdigest()
                    for relative in package_files(existing_package)
                }
            notes += '\n## 续建状态\n基于已保存草稿继续修复，当前包版本须重新验收。文件：' + ', '.join(sorted(workspace.package.files))
            notes += '\n上一轮验证结果：' + json.dumps(
                workspace.package.result_store.present(saved['validation']), ensure_ascii=False)
            if workspace.validation.examples:
                notes += '\n已恢复的宿主固定验收样例：' + json.dumps(workspace.validation.examples, ensure_ascii=False)
            notes += '\n围绕原需求修复输出格式、参数或依赖问题并重新验证；登录或访问受阻时，记录具体观察和下一步。'
            record.event('resumed', draft=str(resume_draft), files=saved['files'], examples=workspace.validation.examples)
            checkpoint()
        elif existing_package is not None:
            from searchos.skills.packaging import package_files, validate_package
            existing = validate_package(existing_package, expected_name=final_dir.name)
            workspace.validation.require_host = bool(host or existing.meta.metadata.get('host'))
            for relative in package_files(existing_package):
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(existing_package / relative, target)
                workspace.package.files.add(relative.as_posix())
            workspace.package.update_base = workspace.package.package_state()
            notes += f"""
Existing package files are seeded in the workspace: {', '.join(sorted(workspace.package.files))}"""
            notes += """
读取并扩展现有包，保留已有能力；在 SKILL.md 更新旧能力与新增能力的调用说明和真实示例。"""
            if not workspace.validation.require_host:
                notes += """
该包覆盖多个来源。沿用现有范围，从已有脚本和 references 确认入口；本次更新的 metadata.host 为可选。"""
            checkpoint()
        if validation_examples is not None:
            workspace.validation.set_validation_examples(validation_examples)
            record.event('host_validation_examples', examples=workspace.validation.examples)
            checkpoint()
        if site_intent:
            if validation_examples is not None:
                raise ValueError('site capability plan cannot replace explicit host examples')
            from searchos.skills.pipeline.access.agents.planner import (
                SitePlannerAgent,
            )
            session = SitePlannerAgent(intent_model or builder_model, workspace, record,
                                       max_turns=planner_max_turns)
            workspace.site_intent = session
            previous_session = (revalidate_from.parent / 'site-session.json' if revalidate_from is not None else
                                resume_draft.parent / 'site-session.json' if resume_draft is not None else site_session_path)
            if on_stage is not None:
                await on_stage('site_intent')
            try:
                planner_resume = (resume_input or {}).get('input') if (resume_input or {}).get('stage') == 'site_intent' else None
                plan = await session.prepare(host, probe_urls, notes, resume=previous_session,
                                             **({'resume_input': planner_resume} if planner_resume else {}))
            except Exception:
                diagnostics['failure_stage'] = 'site_intent'
                raise
            notes += session.builder_notes()
            diagnostics['example_source'] = 'builder'
            diagnostics['capabilities'] = [c['id'] for c in plan['capabilities']]
            record.event('site_plan_ready', plan=plan, contract_version=CONTRACT_VERSION)
            checkpoint()
        if revalidate_from is not None:
            previous = json.loads(revalidate_from.read_text())
            if previous.get('contract_version') != CONTRACT_VERSION:
                raise ValueError('旧版 Access 验收记录仅供查看，请重新创建任务以使用新的角色契约。')
            workspace.validation.last_validation = previous['validation']
            workspace.validation.examples = previous['examples']
            workspace.validation.examples_locked = bool(previous['examples'])
            workspace.validation.validation_rounds = 0
            # 新建补验任务重新观察外部条件；旧执行证据继续保存在报告中。
            for item in workspace.validation.last_validation.get('capability_results', {}).values():
                item.pop('external_blocked', None)
                item.pop('next_action', None)
            workspace.validation.last_validation.pop('candidate_fingerprint', None)
            workspace.validation.last_validation['function_index'] = workspace.validation.function_index()
            workspace.validation.last_validation['regression_commands'] = [
                *workspace.validation.last_validation.get('regression_commands', []),
                *workspace.validation.last_validation.get('external_commands', [])]
            workspace.package.update_base = None
            notes += '\n本次补验原受阻能力，沿用原计划和成功能力；先运行原受阻输入，再按实际结果交付。'
        if on_stage is not None:
            await on_stage('pipeline')
        from searchos.skills.pipeline.access.agents.validator import ValidationAgent
        workspace.validation_agent = ValidationAgent(
            validation_model or builder_model, workspace, record, host=host, notes=user_need,
            on_stage=on_stage, max_turns=validation_max_turns,
        )
        if resume_input and resume_input['stage'] != 'site_intent':
            if resume_input['stage'] == 'access_validation':
                workspace.validation_agent.resume_input = resume_input['input']
            else:
                replayed = await workspace.executor.execute(**resume_input['input'])
                record.event('interrupted_input_replayed', stage='builder', result=replayed)
                if workspace.site_intent:
                    workspace.site_intent.observe('exec', resume_input['input'], replayed, 'builder')
                notes += '\n已重放中断前的原输入：' + json.dumps(record.clean(replayed), ensure_ascii=False)
        from searchos.skills.pipeline.access.agents.builder import AccessBuilderAgent
        if revalidate_from is not None:
            await workspace.send_message('validator', {'request': 'validate'})
            diagnostics['exit_reason'] = 'revalidation_completed'
        else:
            await AccessBuilderAgent(workspace, final_dir, host, probe_urls, notes,
                                     tool_model, max_turns, diagnostics, record, context_model=builder_model).run()

        return publish_current(workspace, final_dir, diagnostics, record)
    except asyncio.CancelledError:
        diagnostics.update(exit_reason='cancelled')
        record.event('cancelled')
        raise
    except Exception as exc:
        stage = diagnostics.get('failure_stage')
        diagnostics.update(exit_reason='site_intent_error' if stage == 'site_intent' else 'execution_error',
                           error_type=type(exc).__name__)
        record.event('execution_error', error_type=type(exc).__name__)
        raise
    finally:
        try:
            try:
                checkpoint()
            except Exception as exc:
                diagnostics['draft_error'] = record.clean(str(exc))
                logger.warning('failed to save access draft for %s', host, exc_info=True)
            # 产物独立于临时工作区；取消仍向上传播，文件先交付再清理。
            try:

                save_artifact(workspace, final_dir, diagnostics, record)
            except Exception as exc:
                diagnostics['artifact_error'] = record.clean(str(exc))
                logger.warning('failed to save access artifact for %s', host, exc_info=True)
            if workspace.site_intent is not None:
                diagnostics['intent_calls'] = workspace.site_intent.state['calls']
                diagnostics['intent_dialogues'] = len(workspace.site_intent.state['dialogues'])
                if failure := workspace.site_intent.state.get('failure'):
                    diagnostics['intent_failure'] = failure
            if workspace.validation_agent is not None:
                diagnostics['validation_calls'] = workspace.validation_agent.calls
                diagnostics['validation_sessions'] = workspace.validation_agent.sessions
                diagnostics['validation_model_usage'] = workspace.validation_agent.usage
            record.summary(diagnostics)
        finally:
            cleanup = asyncio.create_task(browser_session.close())
            try:
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        continue
                cleanup.result()
            finally:
                current_session.reset(browser_token)
                workspace.close()
                shutil.rmtree(staging, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="""Build a SearchOS access skill for a dynamic website.""",
    )
    parser.add_argument("--host", required=True)
    parser.add_argument("--urls", required=True, nargs="+")
    parser.add_argument("--notes", default="")
    parser.add_argument("--output", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-turns", type=int, default=MAX_TURNS)
    parser.add_argument("--max-repair-attempts", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    # The standalone builder shares the same config bootstrap as SearchOS:
    # secrets from .env, then the web/TUI overlay for role/profile bindings.
    try:
        from dotenv import load_dotenv

        for parent in [Path.cwd(), *Path(__file__).resolve().parents]:
            env_file = parent / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                break
    except Exception:
        pass
    from searchos.config.settings_overlay import load_and_apply

    load_and_apply()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    result = asyncio.run(build_skill(
        host=args.host,
        probe_urls=args.urls,
        notes=args.notes,
        output_dir=Path(args.output) if args.output else None,
        model=args.model,
        max_turns=args.max_turns,
        max_repair_attempts=args.max_repair_attempts,
    ))
    if result:
        print(f"skill created at: {result}")
        return 0
    print("failed to create skill", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
