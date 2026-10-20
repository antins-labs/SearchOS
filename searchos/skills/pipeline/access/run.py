"""Access Pipeline 流程：生成 episode、反馈修复、干净包验证与发布。"""
from __future__ import annotations
import argparse
import asyncio
import logging
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from searchos.skills.intent.models import name_for_host
from searchos.skills.pipeline.access.prompt import SYSTEM_PROMPT, user_prompt
from searchos.skills.pipeline.access.tools import BuilderWorkspace, run_tool
from searchos.skills.pipeline.access.valid import validate_access_package

logger = logging.getLogger(__name__)
MAX_TURNS = 45

async def build_skill(
    host: str,
    probe_urls: list[str],
    *,
    notes: str = "",
    output_dir: Path | None = None,
    builder_model: Any = None,
    model: str | None = None,
    max_turns: int = MAX_TURNS,
    discovery_turns: int | None = None,
    validation_examples: list[dict] | None = None,
    existing_package: Path | None = None,
    diagnostics: dict | None = None,
    record_dir: Path | None = None,
    resume_draft: Path | None = None,
    site_intent: bool = False,
    intent_model: Any = None,
    site_session_path: Path | None = None,
    on_stage: Any = None,
) -> Path | None:
    """Build one access skill and return its directory on success.

    The builder uses the already-resolved ``skill_evolver`` chat model so its
    provider, endpoint, key env, protocol, retry policy, and rate limits all
    come from the shared profile/role configuration. Tests and embedding
    callers may inject ``builder_model`` directly. ``model`` is a CLI-only
    wire-model override that retains the rest of the role profile.
    """
    if max_turns < 1:
        raise ValueError('max_turns must be positive')
    if discovery_turns is not None and not 0 <= discovery_turns < max_turns:
        raise ValueError('discovery_turns must be between zero and max_turns - 1')
    from uuid import uuid4
    from searchos.skills.pipeline.access.records import BuildRecord
    final_dir = output_dir or Path("searchos/skills/library/access") / name_for_host(host)
    record = BuildRecord(record_dir or final_dir.parent / '.build-runs' / uuid4().hex)
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update(max_turns=max_turns, turns_attempted=0, turns_completed=0,
                       repair_turns=min(8, max(1, max_turns // 5)), exit_reason='running',
                       record_dir=str(record.root))
    diagnostics['discovery_turns'] = discovery_turns
    diagnostics['example_source'] = 'host' if validation_examples is not None else 'builder'
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
        definitions = list(BuilderWorkspace.TOOL_DEFINITIONS)
        if site_intent:
            from searchos.skills.intent.site import ADVICE_TOOL
            definitions.append(ADVICE_TOOL)
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
    # atomically only after the smoke gate passes (same parent => same
    # filesystem => the rename is atomic).
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".staging_{final_dir.name}_", dir=final_dir.parent))
    workspace = BuilderWorkspace(staging, expected_name=final_dir.name)
    def checkpoint():
        from searchos.skills.pipeline.drafts import save_draft
        pointer = save_draft(record.root, staging, workspace.files, name=final_dir.name,
                             examples=workspace.examples, require_host=workspace.require_host,
                             validation=workspace.last_validation)
        if pointer:
            diagnostics['draft_path'] = str(pointer)
    workspace.checkpoint = checkpoint
    try:
        if resume_draft is not None:
            from searchos.skills.pipeline.drafts import load_draft
            source, saved = load_draft(resume_draft)
            if saved['name'] != final_dir.name:
                raise ValueError('draft name does not match request')
            for relative in saved['files']:
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, target)
                workspace.files.add(relative)
            workspace.examples = saved['examples']
            workspace.require_host = saved['require_host']
            workspace.last_validation = saved['validation']
            workspace.resuming = True
            notes += '\n继续修复已保存草稿，不重新探索或重写已验证能力。文件：' + ', '.join(sorted(workspace.files))
            notes += '\n上一轮验证结果：' + json.dumps(saved['validation'], ensure_ascii=False)
            notes += '\n已恢复的完整验证样例（索引从 0 开始）：' + json.dumps(
                [{'index': index, **example} for index, example in enumerate(workspace.examples)], ensure_ascii=False)
            if validation_examples is None:
                notes += '\n修正已有样例时必须使用 register_example 的 replace_index；追加新样例不会移除旧的失败样例。'
            notes += '\n修复输出格式、参数或依赖问题后重新验证。不得移除用户要求的核心能力来制造成功；遇到登录/访问阻碍请如实说明。'
            record.event('resumed', draft=str(resume_draft), files=saved['files'], examples=workspace.examples)
            checkpoint()
        elif existing_package is not None:
            from searchos.skills.packaging import package_files, validate_package
            existing = validate_package(existing_package, expected_name=final_dir.name)
            workspace.require_host = bool(host or existing.meta.metadata.get('host'))
            for relative in package_files(existing_package):
                target = staging / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(existing_package / relative, target)
                workspace.files.add(relative.as_posix())
            workspace.update_base = workspace.package_state()
            notes += "\nExisting package files are seeded in the workspace: " + ", ".join(sorted(workspace.files))
            notes += "\nRead and extend this package. Preserve existing capabilities and register their regression examples as well as examples of new commands."
            if not workspace.require_host:
                notes += "\nThis existing package has no single host. Preserve its multi-source scope; discover endpoints from existing scripts/references. metadata.host is optional for this update; do not invent a host."
            checkpoint()
        if validation_examples is not None:
            workspace.set_validation_examples(validation_examples)
            record.event('host_validation_examples', examples=workspace.examples)
            checkpoint()
        if site_intent:
            if validation_examples is not None:
                raise ValueError('site capability plan cannot replace explicit host examples')
            from searchos.skills.intent.site import SiteIntentSession, capability_examples
            session = SiteIntentSession(intent_model or builder_model, workspace, record)
            workspace.site_intent = session
            previous_session = resume_draft.parent / 'site-session.json' if resume_draft is not None else site_session_path
            if on_stage is not None:
                await on_stage('site_intent')
            try:
                plan = await session.prepare(host, probe_urls, notes, resume=previous_session)
            except Exception:
                diagnostics['failure_stage'] = 'site_intent'
                raise
            planned_examples = capability_examples(plan)
            if resume_draft is not None and workspace.examples != planned_examples:
                raise ValueError('saved capability plan no longer matches draft examples')
            workspace.set_validation_examples(planned_examples)
            notes += session.builder_notes()
            diagnostics['example_source'] = 'site_intent'
            diagnostics['capabilities'] = [c['id'] for c in plan['capabilities']]
            record.event('site_plan_locked', plan=plan)
            checkpoint()
        if on_stage is not None:
            await on_stage('pipeline')
        return await _build_episode(workspace, final_dir, host, probe_urls, notes, tool_model, max_turns, diagnostics, record)
    except asyncio.CancelledError:
        diagnostics.update(exit_reason='cancelled')
        record.event('cancelled')
        raise
    except Exception as exc:
        diagnostics.update(exit_reason='site_intent_error' if diagnostics.get('failure_stage') == 'site_intent' else 'execution_error', error_type=type(exc).__name__)
        record.event('execution_error', error_type=type(exc).__name__)
        raise
    finally:
        try:
            checkpoint()
            if workspace.site_intent is not None:
                diagnostics['intent_calls'] = workspace.site_intent.state['calls']
                diagnostics['intent_dialogues'] = len(workspace.site_intent.state['dialogues'])
                if failure := workspace.site_intent.state.get('failure'):
                    diagnostics['intent_failure'] = failure
            record.summary(diagnostics)
        finally:
            workspace.close()
            shutil.rmtree(staging, ignore_errors=True)


async def _build_episode(workspace, final_dir, host, probe_urls, notes, tool_model, max_turns, diagnostics=None, record=None):
    logger.info("dynamic builder: host=%s output=%s", host, final_dir)
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    messages: list[Any] = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_prompt(host, probe_urls, notes) + f"\nFinal package name: {final_dir.name}"),
    ]
    if workspace.examples_locked:
        messages.append(HumanMessage(content=(
            '宿主已从原始需求注册并锁定以下验收样例，输出由 stdout 读取；无需 register_example。'
            '不得改写这些输入、输出位置或预期状态。用 exec 诊断错误输入和访问失败，保持其非零失败语义；'
            '未声明 expected_status 的样例要求 ok 和非空 records；边界例按其 expected_status 验收：'
            'empty 要求零退出和空 records，invalid_input 要求非零退出和空 records，二者均须输出 warnings。'
            '用 validate_skill 验证实现。固定样例：\n' + json.dumps(workspace.examples, ensure_ascii=False))))

    repair_start = max_turns - diagnostics['repair_turns']
    discovery_turns = diagnostics.get('discovery_turns')
    initial_package_state = workspace.package_state() if discovery_turns is not None else None
    if discovery_turns is not None:
        messages.append(HumanMessage(content=(
            f'本次总预算 {max_turns} 次模型调用；前 {discovery_turns} 次用于入口发现，'
            f'最后 {diagnostics["repair_turns"]} 次用于验收修复。'
            '发现阶段结束前用 write_file 保存已确认的入口与诊断。'
            '随后必须写出 SKILL.md 和核心脚本，再对具体错误做最小探测。'
            '已有包或草稿的旧文件不算本轮进展；须实际修改实现或保存新的诊断内容，原样重写不解锁 run_python。'
            '可继续使用 exec 调试、validate_skill 验收、读取文件和网页、追问需求 Agent。'
            '不得削减用户核心需求来制造成功，外部阻塞应保存诊断和可恢复草稿。')))
    for turn in range(max_turns):
        if turn == discovery_turns and not workspace.resuming:
            record.event('implementation_phase', turn=turn + 1, files=sorted(workspace.files))
            messages.append(HumanMessage(content=(
                '入口发现预算已用完。现在用 write_file 保存 SKILL.md、scripts/ 下的核心实现和诊断。'
                '没有可信入口时保存阻塞原因，不得猜测接口或输出固定数据。'
                '核心文件齐全且本轮内容已有变化之前，run_python 将被暂缓；优先用 exec 调试包内脚本。')))
        if turn == repair_start or (turn == 0 and workspace.resuming):
            report = await workspace.validate()
            record.event('repair_phase', turn=turn + 1, validation=report)
            if report['valid']:
                diagnostics['exit_reason'] = 'validation_passed'
                break
            if report.get('auth_required'):
                diagnostics['exit_reason'] = 'auth_required'
                break
            guidance = (
                f"进入收尾阶段，剩余 {max_turns - turn} 轮。停止探索新功能。"
                "只保留用户需求所必需的命令，补齐每个已声明命令的 register_example，"
                "运行 validate_skill 并修复失败。使用 read_file/edit_file/write_file/exec 修复现有包。"
                "仍可针对当前错误查询相关资料或做最小对照探测；不要扩展功能或重复失败请求。"
                "遇到外部依赖阻塞时保存诊断，如实说明限制。当前验证结果：\n")
            if workspace.resuming and turn < repair_start:
                guidance = ("从草稿的验证失败处继续。先读取现有文件和样例，修复具体错误，补齐缺失文件，"
                            "保留已工作的功能。先核对核心取数路径是否真的实现；不要在辅助命令的格式问题上耗尽预算。"
                            "需要时可针对失败点查询资料，不要重新全量探索站点。当前验证结果：\n")
            if workspace.examples_locked:
                guidance = ('固定验收样例及其 expected_status 由宿主管理，不能修改或重新注册。修复 CLI 实现、stdout JSON、参数和依赖；'
                            '用 exec 检查负例，用 validate_skill 重新验收，不扩展功能。当前验证结果：\n')
            messages.append(HumanMessage(content=guidance + json.dumps(report, ensure_ascii=False)))
        diagnostics['turns_attempted'] = turn + 1
        phase = 'repair' if turn >= repair_start else ('discovery' if discovery_turns is not None and turn < discovery_turns else 'build')
        diagnostics['phase'] = phase
        record.event('model_started', turn=turn + 1, phase=phase)
        record.summary(diagnostics)
        logger.info("dynamic builder: turn %s/%s", turn + 1, max_turns)
        try:
            msg = await tool_model.ainvoke(messages)
        except Exception as exc:
            diagnostics.update(exit_reason='model_error', model_error_type=type(exc).__name__, model_error=record.clean(str(exc)))
            record.event('model_error', turn=turn + 1, error_type=type(exc).__name__)
            logger.warning("dynamic builder model call failed for %s", host, exc_info=True)
            break

        diagnostics['turns_completed'] = turn + 1
        usage = getattr(msg, 'usage_metadata', None) or {}
        for key in ('input_tokens', 'output_tokens', 'total_tokens'):
            if isinstance(usage.get(key), int):
                diagnostics['model_usage'][key] = diagnostics['model_usage'].get(key, 0) + usage[key]
        tool_calls = getattr(msg, "tool_calls", None) or []
        record.event('model_completed', turn=turn + 1, content=msg.content, tool_calls=tool_calls, usage=usage)
        record.summary(diagnostics)
        # Preserve the provider-normalized assistant message, including tool
        # calls, so the next turn remains valid for every supported protocol.
        messages.append(msg)

        if not tool_calls:
            report = await workspace.validate()
            record.event('validation', turn=turn + 1, report=report)
            if report["valid"]:
                diagnostics['exit_reason'] = 'validation_passed'
                break
            if report.get('auth_required'):
                diagnostics['exit_reason'] = 'auth_required'
                logger.info('dynamic builder awaits user authentication: %s', host)
                break
            messages.append(HumanMessage(content="校验失败，请修复后继续：\n" + json.dumps(report, ensure_ascii=False)))
            continue

        for tc in tool_calls:
            record.event('tool_started', turn=turn + 1, name=tc.get('name'), call_id=tc.get('id'))
            has_core = 'SKILL.md' in workspace.files and any(p.startswith('scripts/') for p in workspace.files)
            if (discovery_turns is not None and turn >= discovery_turns and tc.get('name') == 'run_python'
                    and (not has_core or workspace.package_state() == initial_package_state)):
                result = ToolMessage(content=json.dumps({'error': 'discovery_budget_exhausted',
                    'next_action': '先补齐 SKILL.md 和核心脚本，并落实本轮内容变化。已有包可先将新证据写入 references/diagnosis.md；'
                                   '原样重写不解锁。可继续 exec 调试、validate_skill 验收、读取文件和网页或追问需求 Agent；不得伪造成功。'}, ensure_ascii=False),
                    tool_call_id=tc['id'])
                record.event('discovery_call_deferred', turn=turn + 1, name=tc.get('name'))
            else:
                result = await run_tool(workspace, tc)
            messages.append(result)
            record.event('tool_result', turn=turn + 1, name=tc.get('name'), call_id=tc.get('id'), content=result.content)
    else:
        diagnostics['exit_reason'] = 'max_turns'
        logger.warning("dynamic builder reached max turns for %s", host)
    record.event('generation_stopped', reason=diagnostics['exit_reason'], examples=workspace.examples)
    record.summary(diagnostics)

    # Publish only files written through write_file, then validate the exact package.
    with tempfile.TemporaryDirectory(prefix=".builder-publish-", dir=final_dir.parent) as temporary:
        candidate = Path(temporary) / final_dir.name
        candidate.mkdir()
        for relative in sorted(workspace.files):
            source = workspace._resolve_inside(relative)
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        report = workspace.revision_error() or await validate_access_package(candidate, final_dir.name, workspace.examples, require_host=workspace.require_host)
        workspace.last_validation = report
        if diagnostics is not None:
            diagnostics.update(report)
        record.event('final_validation', report=report)
        record.summary(diagnostics)
        if not report["valid"]:
            logger.warning("dynamic builder validation failed for %s: %s", host, report)
            return None
        from searchos.skills.pipeline.store import publish_package
        publish_package(candidate, final_dir)
    return final_dir

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a SearchOS access skill for a dynamic website.",
    )
    parser.add_argument("--host", required=True)
    parser.add_argument("--urls", required=True, nargs="+")
    parser.add_argument("--notes", default="")
    parser.add_argument("--output", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-turns", type=int, default=MAX_TURNS)
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
    from searchos.config.web_overlay import load_and_apply

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
    ))
    if result:
        print(f"skill created at: {result}")
        return 0
    print("failed to create skill", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
