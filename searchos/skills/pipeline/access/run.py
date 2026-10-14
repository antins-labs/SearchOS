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
    existing_package: Path | None = None,
    diagnostics: dict | None = None,
    record_dir: Path | None = None,
    resume_draft: Path | None = None,
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
                       repair_turns=min(8, max(1, max_turns // 5)), exit_reason='running',
                       record_dir=str(record.root))
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
        tool_model = builder_model.bind_tools(BuilderWorkspace.TOOL_DEFINITIONS)
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
            notes += "\nExisting package files are seeded in the workspace: " + ", ".join(sorted(workspace.files))
            notes += "\nRead and extend this package. Preserve existing capabilities and register their regression examples as well as examples of new commands."
            if not workspace.require_host:
                notes += "\nThis existing package has no single host. Preserve its multi-source scope; discover endpoints from existing scripts/references. metadata.host is optional for this update; do not invent a host."
            checkpoint()
        return await _build_episode(workspace, final_dir, host, probe_urls, notes, tool_model, max_turns, diagnostics, record)
    except asyncio.CancelledError:
        diagnostics.update(exit_reason='cancelled')
        record.event('cancelled')
        raise
    except Exception as exc:
        diagnostics.update(exit_reason='execution_error', error_type=type(exc).__name__)
        record.event('execution_error', error_type=type(exc).__name__)
        raise
    finally:
        try:
            checkpoint()
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

    repair_start = max_turns - diagnostics['repair_turns']
    for turn in range(max_turns):
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
            messages.append(HumanMessage(content=guidance + json.dumps(report, ensure_ascii=False)))
        diagnostics['turns_attempted'] = turn + 1
        record.event('model_started', turn=turn + 1, phase='repair' if turn >= repair_start else 'build')
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
        tool_calls = getattr(msg, "tool_calls", None) or []
        record.event('model_completed', turn=turn + 1, content=msg.content, tool_calls=tool_calls)
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
        report = await validate_access_package(candidate, final_dir.name, workspace.examples, require_host=workspace.require_host)
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
