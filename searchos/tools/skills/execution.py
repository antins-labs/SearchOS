"""技能加载快照、受限命令执行与结果页面注册。"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from langchain_core.tools import InjectedToolCallId, tool

from searchos.skills.runtime.paths import resolve_resource_file, skill_workspace_dir
from searchos.tools.search_state import (
    _current_agent_var,
    _current_task_id_var,
    _source_scope_var,
    _workspace_var,
)


WORK_LOCK_WAIT_TIMEOUT_S = 300.0


async def _acquire_work_lock(lock) -> None:
    """同任务的并行调用等待共享目录；不阻塞事件循环，取消时不遗留抢锁线程。"""
    try:
        async with asyncio.timeout(WORK_LOCK_WAIT_TIMEOUT_S):
            while True:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except BlockingIOError:
                    await asyncio.sleep(0.05)
    except TimeoutError as exc:
        raise ValueError("timed out waiting for this task's work directory; command was not started") from exc


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(_json(value), encoding="utf-8")
    temporary.replace(path)


def _context() -> tuple[Path, str]:
    ws = _workspace_var.get()
    if ws is None:
        raise ValueError("skill execution requires a bound task workspace")
    identity = _current_task_id_var.get() or _current_agent_var.get()
    key = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return ws.path.resolve(), key


def _skill(name: str):
    from searchos.config.settings import settings
    from searchos.skills.catalog.registry import SKILL_BLACKLIST
    from searchos.tools.skills.catalog import _registry, _skill_allowed

    if not settings.enable_skills or name in SKILL_BLACKLIST:
        raise ValueError("skill is disabled")
    registry = _registry()
    skill = registry.get(name) if registry is not None else None
    if skill is None or skill.meta.availability.value != "enabled" or not _skill_allowed(skill):
        raise ValueError(f"skill is unavailable: {name}")
    return skill


def _binding_path(root: Path, key: str, name: str) -> Path:
    """名称迁移不改变已运行任务固定的旧包版本。"""
    from searchos.skills.names import canonical_skill_name, legacy_names
    canonical = canonical_skill_name(name)
    names = dict.fromkeys([name, canonical, *[old for old, new in legacy_names().items() if new == canonical]])
    for candidate in names:
        path = skill_workspace_dir(root, "bindings") / key / f"{hashlib.sha256(candidate.encode()).hexdigest()}.json"
        if path.is_file():
            return path
    return skill_workspace_dir(root, "bindings") / key / f"{hashlib.sha256(canonical.encode()).hexdigest()}.json"


def load_package(name: str) -> dict[str, Any]:
    """固定本任务的技能版本；后续读取和执行使用同一快照。"""
    from searchos.skills.core.schema import parse_skill_file
    from searchos.skills.packaging import package_fingerprint, snapshot_package

    skill = _skill(name)
    name = skill.meta.name
    root, key = _context()
    binding_path = _binding_path(root, key, name)
    if binding_path.exists():
        binding = json.loads(binding_path.read_text())
    else:
        source = Path(skill.file_path).resolve().parent
        fingerprint = package_fingerprint(source)
        destination = skill_workspace_dir(root, "packages") / fingerprint
        if not destination.exists():
            try:
                snapshot_package(source, destination)
            except FileExistsError:
                pass
        if package_fingerprint(destination) != fingerprint:
            raise ValueError("skill package changed during snapshot; reload and retry")
        binding = {"name": name, "package_hash": fingerprint, "directory": str(destination)}
        _write_json(binding_path, binding)
    directory = Path(binding["directory"])
    if package_fingerprint(directory) != binding["package_hash"]:
        raise ValueError("loaded skill snapshot hash changed")
    frozen = parse_skill_file(directory, expected_name=binding["name"])
    resources = sorted(str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file())
    legacy = (directory / "executor.py").is_file() and not any(
        p.name == "SKILL.md" for p in directory.iterdir()
    )
    answer = {
        **binding, "body": frozen.body, "category": frozen.meta.category.value,
        "description": frozen.meta.description, "compatibility": frozen.meta.compatibility,
        "availability": skill.meta.availability.value,
        "resources": resources[:200], "resources_truncated": len(resources) > 200,
        "work_directory": str(skill_workspace_dir(root, "work") / key),
        "execution": "legacy-executor" if legacy else "cli",
    }
    if legacy:
        manifest = directory / "manifest.yaml"
        if manifest.is_file():
            import yaml
            answer["legacy_parameters"] = (yaml.safe_load(manifest.read_text()) or {}).get("params_schema", {})
        answer["invocation"] = 'exec(skill=name, argv=["legacy-executor", "--params", "<JSON object>"])'
    else:
        answer["invocation"] = "exec(skill=name, argv=[interpreter, package_relative_script, ...arguments])"
    return answer


def _loaded(name: str) -> dict[str, Any]:
    name = _skill(name).meta.name  # Resolve old names and recheck availability.
    root, key = _context()
    path = _binding_path(root, key, name)
    if not path.is_file():
        raise ValueError(f"load_skill({name!r}) before executing or reading its resources")
    binding = json.loads(path.read_text())
    from searchos.skills.packaging import package_fingerprint
    if package_fingerprint(Path(binding["directory"])) != binding["package_hash"]:
        raise ValueError("loaded skill snapshot hash changed")
    return binding


def execution_started(tool_call_id: str) -> bool:
    """供取消预算结算读取宿主保存的实际启动信号；不可读时保守返回 False。"""
    try:
        root, key = _context()
        receipt = skill_workspace_dir(root, "calls") / key / (hashlib.sha256(tool_call_id.encode()).hexdigest() + ".json")
        call = json.loads(receipt.read_text())
        if isinstance(call.get("result"), dict):
            return call["result"].get("started") is True
        identifier = call.get("execution_id", "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", identifier):
            return False
        record = json.loads((skill_workspace_dir(root, "executions") / identifier / "record.json").read_text())
        return record.get("started") is True
    except (ValueError, OSError, TypeError, AttributeError):
        return False


@tool
async def load_skill(skill_name: str) -> str:
    """Read instructions and freeze a skill package for this task before exec."""
    try:
        package = load_package(skill_name)
        fields = (
            "name", "body", "category", "description", "compatibility", "resources",
            "execution", "invocation", "legacy_parameters",
        )
        visible = {key: package[key] for key in fields if key in package}
        if package.get("resources_truncated"):
            visible["resources_truncated"] = True
        return json.dumps(visible, ensure_ascii=False)
    except (ValueError, OSError) as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


@tool
async def read_skill_file(
    skill: str, path: str,
    offset: int = 0, limit: int = 12000,
) -> str:
    """Read a loaded skill package reference. Read execution results with open/find.

    Paths are relative to the loaded skill package.
    Text is bounded; use offset to read the next window.
    """
    try:
        binding = _loaded(skill)
        base = Path(binding["directory"])
        file = resolve_resource_file(base, path)
        if file.stat().st_size > 2_000_000:
            raise ValueError("file exceeds the text reader limit; process it with a bundled script")
        text = file.read_text(encoding="utf-8")
        start, count = max(0, offset), min(24000, max(1, limit))
        return _json({"path": path, "offset": start, "text": text[start:start + count],
                      "next_offset": start + count if start + count < len(text) else None})
    except (ValueError, OSError) as exc:
        return _json({"error": str(exc)})


async def _legacy(directory: Path, argv: list[str], executions: Path, timeout: float, execution_id: str, proxy_mode: str = 'inherit') -> dict:
    from searchos.skills.runtime.legacy.executor_runtime import ExecutionPolicy, run_executor

    if len(argv) != 3 or argv[1] != "--params":
        raise ValueError('legacy usage: ["legacy-executor", "--params", "<JSON object>"]')
    params = json.loads(argv[2])
    if not isinstance(params, dict):
        raise ValueError("legacy params must be a JSON object")
    if not (directory / "executor.py").is_file():
        raise ValueError("this skill has no legacy executor")
    if any(p.name == "SKILL.md" for p in directory.iterdir()):
        raise ValueError("portable packages cannot use the legacy executor adapter")
    saved = executions / execution_id
    saved.mkdir(parents=True)
    workspace = _workspace_var.get()
    query = ""
    if workspace is not None:
        try:
            query = workspace.load_state().intent or ""
        except (AttributeError, OSError, ValueError):
            pass
    try:
        result = await run_executor(directory, params, query=query,
                                    policy=ExecutionPolicy.access(timeout_s=timeout, proxy_mode=proxy_mode))
    except asyncio.CancelledError:
        _write_json(saved / "record.json", {"execution_id": execution_id,
                    "status": "cancelled", "started": False, "legacy": True, "artifacts": []})
        raise
    artifact = saved / "artifacts" / "result.json"
    _write_json(artifact, result)
    failed = bool(result.get("error")) or result.get("success") is False
    record = {
        "execution_id": execution_id, "status": "timed_out" if result.get("error_type") == "timeout" else ("failed" if failed else "completed"),
        "exit_code": 1 if failed else 0, "started": True,
        "timed_out": result.get("error_type") == "timeout",
        "stdout": "Legacy result saved as result.json", "stderr": str(result.get("error", "")),
        "truncated": False, "legacy": True,
        "artifacts": [{"id": "result.json", "path": "result.json", "media_type": "application/json",
                       "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}],
    }
    _write_json(saved / "record.json", record)
    return record


def _execution_response(result: dict) -> tuple[str, dict]:
    # 回执负责引导阅读；原始输出保存在页面与 artifact，避免模型把执行成功
    # 误当成已阅读、已抽取。错误诊断仍保留有界预览。
    visible = {key: result[key] for key in ("execution_id", "status", "exit_code", "page_url", "index_page_url") if key in result}
    if result.get("page_url"):
        visible["read_result"] = {"tool": "open", "arguments": {"id_or_url": result["page_url"]}}
        visible["reading_note"] = "Read the saved result with open before continuing retrieval."
    for key in ("error", "page_error", "stdout", "stderr"):
        value = result.get(key)
        if not value:
            continue
        if key in {"stdout", "stderr"}:
            if key == "stdout" and result.get("page_url") and not result.get("page_error"):
                continue
            value = str(value or "")
            if len(value) > 2000:
                value = value[:2000] + "\n[preview truncated; full output saved in execution logs]"
        visible[key] = value
    for key in ("auth_required", "truncated", "replayed"):
        if result.get(key):
            visible[key] = True
    if result.get("pages_total", 0) > 1:
        visible["pages"] = result.get("pages", [])
        visible["pages_total"] = result["pages_total"]
    if result.get("unrendered"):
        visible["unrendered"] = result["unrendered"]
    return _json(visible), {"execution": result, "outcome": {"status": result["status"]}}


@tool("exec", response_format="content_and_artifact")
async def exec_skill(
    skill: str, argv: list[str], tool_call_id: Annotated[str, InjectedToolCallId],
    stdin: str = "", timeout_s: float = 60, proxy_mode: Literal['inherit', 'direct', 'proxy'] = 'inherit',
) -> tuple[str, dict]:
    """Run a bundled Python, Shell or Node script from a loaded skill.

    argv starts with python/python3, bash/sh or node and a package-relative script path. No shell strings or inline code. cwd is the task work directory. Concurrent calls within one task wait for this directory; different tasks run independently.
    Returns an execution receipt with read_result and saved page URLs. Follow read_result with open, then use find or open(loc=...) to inspect relevant windows before further retrieval. exec itself does not extract evidence.
    proxy_mode is inherit (environment), direct (no application proxy), or proxy (require a configured proxy). Browser scripts must honor these environment defaults.
    Legacy skills accept ["legacy-executor", "--params", "<JSON object>"].
    """
    try:
        from searchos.skills.runtime.network import validate_proxy_mode
        validate_proxy_mode(proxy_mode)
        if (_source_scope_var.get() or {}).get("mode") == "local":
            raise ValueError("Access Skill execution is unavailable in Local source mode")
        binding = _loaded(skill)
        root, key = _context()
        if not math.isfinite(timeout_s):
            raise ValueError("timeout must be finite")
        timeout = min(120.0, max(0.1, timeout_s))
        if not argv or not all(isinstance(a, str) and "\x00" not in a for a in argv):
            raise ValueError("argv must contain nonempty command arguments without NUL")
        if len(_json(argv)) + len(stdin) > 128_000:
            raise ValueError("command input exceeds 128000 characters")
        receipt = skill_workspace_dir(root, "calls") / key / (hashlib.sha256(tool_call_id.encode()).hexdigest() + ".json")
        request_hash = hashlib.sha256(_json({"skill": skill, "package_hash": binding["package_hash"],
                    "argv": argv, "stdin": stdin, "timeout": timeout, "proxy_mode": proxy_mode}).encode()).hexdigest()
        work = skill_workspace_dir(root, "work") / key
        work.mkdir(parents=True, exist_ok=True)
        # Lock before reading/writing receipts: concurrent processes cannot both
        # accept the same call or overwrite each other's pending receipt.
        lock = (skill_workspace_dir(root, "work") / f".{key}.lock").open("a")
        try:
            await _acquire_work_lock(lock)
        except BaseException:
            lock.close()
            raise
        accepted = False
        result = None
        try:
            if receipt.exists():
                previous = json.loads(receipt.read_text())
                if previous.get("request_hash") != request_hash:
                    raise ValueError("tool call id was already used with a different request")
                result = previous.get("result") or {
                    "status": "blocked", "error": "previous execution outcome unknown; inspect saved runs before retrying",
                }
                result = {**result, "started": False, "replayed": True}
                return _execution_response(result)
            execution_id = 'exec-' + uuid4().hex
            _write_json(receipt, {"state": "pending", "request_hash": request_hash, "execution_id": execution_id,
                                 "skill": skill, "package_hash": binding["package_hash"]})
            accepted = True
            if argv[0] == "legacy-executor":
                if stdin:
                    raise ValueError("legacy executor does not accept stdin")
                result = await _legacy(Path(binding["directory"]), argv, skill_workspace_dir(root, "executions"), timeout, execution_id, proxy_mode)
            else:
                from searchos.skills.runtime.command_runtime import run_command
                result = await run_command(
                    Path(binding["directory"]), argv, work_dir=work,
                    execution_dir=skill_workspace_dir(root, "executions"), stdin=stdin, timeout_s=timeout, network=True,
                    execution_id=execution_id, proxy_mode=proxy_mode,
                )
            if result.get("execution_id"):
                _write_json(skill_workspace_dir(root, "executions") / result["execution_id"] / "binding.json",
                            {**binding, "task_key": key})
            if result.get("execution_id"):
                from searchos.tools.simple_browser.result_pages import register_execution_pages
                try:
                    result.update(register_execution_pages(result, binding,
                        skill_workspace_dir(root, "executions") / result["execution_id"], key))
                except (ValueError, OSError, TypeError) as exc:
                    # Execution already happened: preserve its status and budget.
                    result["page_error"] = str(exc)
            _write_json(receipt, {"state": "complete", "request_hash": request_hash, "result": result})
        except (ValueError, OSError) as exc:
            if accepted:
                failure = {"status": "blocked", "started": bool(result and result.get("started")), "error": str(exc)}
                _write_json(receipt, {"state": "complete", "request_hash": request_hash, "result": failure})
                return _execution_response(failure)
            raise
        except asyncio.CancelledError:
            _write_json(skill_workspace_dir(root, "executions") / execution_id / "binding.json",
                        {**binding, "task_key": key})
            _write_json(receipt, {"state": "cancelled", "request_hash": request_hash, "execution_id": execution_id,
                       "result": {"status": "cancelled", "execution_id": execution_id,
                                  "started": execution_started(tool_call_id)}})
            raise
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
        return _execution_response(result)
    except (ValueError, OSError) as exc:
        result = {"status": "blocked", "error": str(exc), "started": False}
        return _execution_response(result)

