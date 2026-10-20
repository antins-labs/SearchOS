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
    from uuid import uuid4
    from searchos.skills.pipeline.access.records import BuildRecord
    final_dir = output_dir or Path("searchos/skills/library/access") / name_for_host(host)
    record = BuildRecord(record_dir or final_dir.parent / '.build-runs' / uuid4().hex)
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update(max_turns=max_turns, turns_attempted=0, turns_completed=0,
                       exit_reason='running', record_dir=str(record.root))
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
    workspace.expected_host = host
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
            if existing_package is not None:
                # 恢复更新任务时也要与已安装包比较，不能把旧包通过样例当成修复完成。
                import hashlib
                from searchos.skills.packaging import package_files
                workspace.update_base = {
                    relative.as_posix(): hashlib.sha256((existing_package / relative).read_bytes()).hexdigest()
                    for relative in package_files(existing_package)
                }
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
            # 需求阶段中断时，草稿可能已有文件但尚未保存验收样例。
            # 从恢复的计划编译首次样例；已有样例仍必须逐项匹配。
            if resume_draft is not None and workspace.examples and workspace.examples != planned_examples:
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
        stage = diagnostics.get('failure_stage')
        diagnostics.update(exit_reason='site_intent_error' if stage == 'site_intent' else 'execution_error',
                           error_type=type(exc).__name__)
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
    from langchain_core.messages import HumanMessage, SystemMessage

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

    for turn in range(max_turns + 1):
        closing = turn == max_turns
        guidance = (
            '常规调用额度已用完。这是额外的一次收尾调用；停止新探索，不调用网页研究或 run_python。'
            '依据已有结果完成文件修改、运行 CLI 和 validate_skill；失败时如实保留问题，不会再有修复调用。'
            if closing else
            f'本轮是第 {turn + 1}/{max_turns} 次常规模型调用；按需探索、实现并调用 validate_skill 验收。'
        )
        messages.append(HumanMessage(content=guidance))
        diagnostics['turns_attempted'] = turn + 1
        record.event('model_started', turn=turn + 1, closing=closing)
        record.summary(diagnostics)
        logger.info("dynamic builder: turn %s/%s", turn + 1, max_turns + 1)
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
        messages.append(msg)
        for tc in tool_calls:
            record.event('tool_started', turn=turn + 1, name=tc.get('name'), call_id=tc.get('id'))
            result = await run_tool(workspace, tc)
            messages.append(result)
            record.event('tool_result', turn=turn + 1, name=tc.get('name'), call_id=tc.get('id'), content=result.content)

        # 完成回复或额度结束时验收当前文件；同轮先通过再修改也必须重验。
        changed = workspace.checked_state != workspace.validation_state()
        if changed and (not tool_calls or turn >= max_turns - 1 or workspace.last_validation.get('valid')):
            report = await workspace.validate()
            record.event('validation', turn=turn + 1, report=report)
            if not report['valid']:
                messages.append(HumanMessage(content='校验失败，请修复后继续：\n' + json.dumps(report, ensure_ascii=False)))
        if workspace.checked_state == workspace.validation_state():
            if workspace.last_validation.get('valid'):
                diagnostics['exit_reason'] = 'validation_passed'
                break
            if workspace.last_validation.get('auth_required'):
                diagnostics['exit_reason'] = 'auth_required'
                break
            if not tool_calls and not changed:
                messages.append(HumanMessage(content='校验失败，请修复后继续：\n' + json.dumps(workspace.last_validation, ensure_ascii=False)))
    else:
        diagnostics['exit_reason'] = 'max_turns'
        logger.warning("dynamic builder exhausted regular and closing calls for %s", host)
    record.event('generation_stopped', reason=diagnostics['exit_reason'], examples=workspace.examples)

    report = workspace.last_validation
    if workspace.checked_state != workspace.validation_state():
        report = {'valid': False, 'stage': 'validation',
                  'error': 'generation stopped before the current package was validated'}
    diagnostics.update(report)
    record.event('final_validation', report=report)
    record.summary(diagnostics)
    if not report.get('valid'):
        logger.warning("dynamic builder validation failed for %s: %s", host, report)
        return None

    # 发布与刚验收相同的文件，不在预算循环之外再引入一次可能失败的网络验收。
    with tempfile.TemporaryDirectory(prefix=".builder-publish-", dir=final_dir.parent) as temporary:
        candidate = Path(temporary) / final_dir.name
        candidate.mkdir()
        for relative in sorted(workspace.files):
            source = workspace._resolve_inside(relative)
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
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
