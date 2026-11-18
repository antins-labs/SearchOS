"""通用 Exec：持久文件、独立进程、任务范围内的宿主能力桥。"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import math
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from langchain_core.tools import InjectedToolCallId, tool

from searchos.skills.runtime.paths import skill_workspace_dir
from searchos.tools.exec import artifacts
from searchos.tools.exec.bridge import HostBridge
from searchos.tools.exec import workspace as exec_workspace
from searchos.tools.search_state import _current_agent_var, _current_task_id_var, _source_scope_var

# 兼容旧导入路径；测试可 monkeypatch 这些模块属性。
_acquire_work_lock = exec_workspace.acquire_work_lock
_context = exec_workspace.context
_write_json = exec_workspace.write_json


def response(result):
    visible = {
        k: result[k]
        for k in (
            "execution_id",
            "status",
            "exit_code",
            "stdout",
            "stderr",
            "error",
            "result_ref",
            "page_url",
            "read_result",
            "artifacts",
            "replayed",
        )
        if k in result
    }
    for stream in ("stdout", "stderr"):
        if stream in visible:
            visible[stream] = str(visible[stream]).encode()[:8000].decode(errors="ignore")
    visible["streams"] = {}
    for stream in ("stdout", "stderr"):
        if stream not in visible:
            continue
        metadata = result.get("streams", {}).get(stream, {})
        total_chars = metadata.get("total_chars")
        if total_chars is None and not metadata.get("preview_truncated"):
            total_chars = len(str(result[stream]))
        visible["streams"][stream] = {"total_chars": total_chars}
        if metadata.get("page_url"):
            visible["streams"][stream]["page_url"] = metadata["page_url"]
        if metadata.get("log_truncated"):
            visible["streams"][stream]["log_truncated"] = True
    visible["artifacts"] = visible.get("artifacts", [])[:20]
    if result.get("child_results"):
        visible["child_results"] = {
            **result["child_results"], "items": deepcopy(result["child_results"]["items"][:20]),
        }
    if "error" in visible:
        visible["error"] = str(visible["error"]).encode()[:2000].decode(errors="ignore")
    while True:
        children = visible.get("child_results")
        if children:
            children.update(shown=len(children["items"]), truncated=len(children["items"]) < children["total"])
        outputs = [visible, *(children["items"] if children else [])]
        for output in outputs:
            for stream, metadata in output["streams"].items():
                shown_chars = len(output.get(stream, ""))
                metadata.update(
                    shown_chars=shown_chars,
                    truncated=metadata["total_chars"] is None or shown_chars < metadata["total_chars"],
                )
        if len(json.dumps(visible, ensure_ascii=False).encode()) <= 24000:
            break
        previews = [(output, stream) for output in outputs for stream in ("stdout", "stderr")
                    if output.get(stream)]
        if previews:
            output, stream = max(previews, key=lambda pair: len(pair[0][pair[1]].encode()))
            output[stream] = output[stream][:len(output[stream]) // 2]
        elif children and children["items"]:
            children["items"].pop()
        elif visible["artifacts"]:
            visible["artifacts"].pop()
        else:
            raise ValueError("Exec result metadata exceeds the 24000-byte response budget")
    return json.dumps(visible, ensure_ascii=False), {
        "execution": result,
        "outcome": {"status": result["status"]},
        "source_observations": result.get("source_observations", []),
    }


@tool("exec", response_format="content_and_artifact", parse_docstring=True)
async def exec_code(
    tool_call_id: Annotated[str, InjectedToolCallId],
    argv: list[str] | None = None,
    code: str | None = None,
    inputs: list[str] | None = None,
    stdin: str = "",
    timeout_s: float = 60,
):
    """Run a command or Python program to retrieve data, compute results or generate files. Each
    call starts a fresh process in the task's persistent working directory.

    Supply exactly one of argv or code. Use code for loops, filtering, aggregation, parsing saved
    inputs, and orchestration. Import searchos_sdk in Python to call loaded Access Skills as
    functions; see load_skill for the skill's usage and parameters. Save files to retain data
    across calls.

    Returns status, exit_code, stdout/stderr previews and artifact refs. streams entries give
    shown_chars, total_chars, truncated and a page_url for saved text. Counts use Unicode
    characters. The total_chars field may be null when unavailable. log_truncated means the
    capture limit was reached. Use open(id_or_url=page_url) to read beyond a preview and leave unavailable data
    unknown.
    child_results includes each reported skill's arguments, status and stdout/stderr previews (up
    to 512 characters per stream). Per-child streams give the same counts and saved URLs. The
    response budget may shorten previews or omit entries. Compare shown/total/truncated and use
    open/find on the index page_url or a stream URL to inspect raw output, including results
    filtered from the program's own stdout.

    Args:
        tool_call_id: Execution identifier supplied by the tool runtime.
        argv: Command and arguments as separate strings for one invocation, without shell parsing.
            Omit when using code.
        code: Python source up to 100000 UTF-8 bytes. Use for loops, filtering, aggregation or
            skill orchestration via searchos_sdk. Omit when using argv.
        inputs: Existing artifact refs or previously read page URLs to expose as read-only files.
            SEARCHOS_INPUTS_FILE identifies the JSON mapping of each input to path, media_type and
            source. Defaults to no inputs.
        stdin: Text for the process's standard input, empty by default.
        timeout_s: Total execution time in seconds, including host capability calls. Must be greater
            than 0 and at most 300, default 60.
    """
    try:
        if (argv is None) == (code is None):
            raise ValueError("provide exactly one of argv or code")
        if (
            not isinstance(timeout_s, (float, int))
            or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 300
        ):
            raise ValueError("timeout_s must be between 0 and 300")
        if code is not None and (not code.strip() or len(code.encode()) > 100_000):
            raise ValueError("code must contain 1–100000 bytes")
        if argv is not None and (
            not argv or any(not isinstance(a, str) or "\0" in a for a in argv)
        ):
            raise ValueError("argv must be a nonempty list of strings")
        if len(json.dumps([argv, code, inputs, stdin]).encode()) > 128_000:
            raise ValueError("command input exceeds 128000 bytes")
        root, key = _context()
        request = {
            "argv": argv,
            "code": code,
            "inputs": inputs or [],
            "stdin": stdin,
            "timeout_s": timeout_s,
            "network_enabled": (
                _current_agent_var.get().startswith("search_agent")
                and (_source_scope_var.get() or {}).get("mode") != "local"
            ),
        }
        from searchos.network import current_context

        request["network"] = current_context().config.fingerprint
        request_hash = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        receipt = (
            skill_workspace_dir(root, "calls")
            / key
            / (hashlib.sha256(tool_call_id.encode()).hexdigest() + ".json")
        )
        work = root / "execution" / "work" / key
        work.mkdir(parents=True, exist_ok=True)
        lock = (work.parent / ("." + key + ".lock")).open("a")
        try:
            deadline = asyncio.get_running_loop().time() + timeout_s
            async with asyncio.timeout(timeout_s):
                await _acquire_work_lock(lock)
            if receipt.exists():
                previous = json.loads(receipt.read_text())
                if previous.get("request_hash") != request_hash:
                    raise ValueError("tool call id was already used with another request")
                result = previous.get("result") or {
                    "status": "blocked",
                    "error": "previous execution outcome unknown",
                }
                return response({**result, "replayed": True, "started": False})
            request["timeout_s"] = max(0.001, deadline - asyncio.get_running_loop().time())
            return await execute(request, root, key, work, receipt, request_hash)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
    except (ValueError, OSError, TimeoutError) as exc:
        return response(
            {"status": "blocked", "error": str(exc) or "execution wait timed out", "started": False}
        )


async def execute(request, root, key, work, receipt, request_hash):
    from searchos.config.settings import settings
    from searchos.skills.runtime.command_runtime import run_command

    if settings.enable_skills:
        from searchos.tools.skills.capability import register

        register()

    execution_id = "exec-" + uuid4().hex
    directory = skill_workspace_dir(root, "executions")
    saved = directory / execution_id
    package = root / "execution" / "programs" / execution_id
    package.mkdir(parents=True)
    sdk_source = Path(__file__).with_name("sdk.py").read_text()
    (package / "searchos_sdk.py").write_text(sdk_source)
    mapping, reads = {}, []
    for ref in request["inputs"]:
        metadata, path = artifacts.read(ref)
        mapping[ref] = {
            "path": str(path),
            "media_type": metadata["media_type"],
            "source": metadata["source"],
        }
        reads.append(path)
    manifest = package / "inputs.json"
    _write_json(manifest, mapping)
    argv = request["argv"]
    if request["code"] is not None:
        (package / "main.py").write_text(request["code"])
        argv = ["python", "main.py"]
    _write_json(
        receipt, {"state": "pending", "request_hash": request_hash, "execution_id": execution_id}
    )
    result = None
    bridge = None
    try:
        with tempfile.TemporaryDirectory(prefix="sf-exec-", dir="/tmp") as temporary:
            socket_path = Path(temporary).resolve() / "rpc.sock"
            deadline = asyncio.get_running_loop().time() + request["timeout_s"]
            async with HostBridge(root, key, execution_id, socket_path, deadline) as bridge:
                result = await run_command(
                    package,
                    argv,
                    work_dir=work,
                    execution_dir=directory,
                    execution_id=execution_id,
                    timeout_s=request["timeout_s"],
                    stdin=request["stdin"],
                    network=request["network_enabled"],
                    read_only_paths=reads,
                    runtime_env={
                        "SEARCHOS_BRIDGE_SOCKET": str(socket_path),
                        "SEARCHOS_RUN_TOKEN": bridge.token,
                        "SEARCHOS_INPUTS_FILE": str(manifest),
                    },
                    ipc_socket=socket_path,
                    network_policy=source_network_policy(),
                )
    except asyncio.CancelledError:
        result = (
            json.loads((saved / "record.json").read_text())
            if (saved / "record.json").exists()
            else {
                "execution_id": execution_id,
                "status": "cancelled",
                "started": False,
            }
        )
        raise
    except (ValueError, OSError, TimeoutError) as exc:
        result = (
            json.loads((saved / "record.json").read_text())
            if (saved / "record.json").exists()
            else {
                "execution_id": execution_id,
                "status": "blocked",
                "started": False,
            }
        )
        result["error"] = str(exc)
    finally:
        if result is not None:
            result["source_observations"] = bridge.observations if bridge else []
            result["child_executions"] = (
                [r["execution_id"] for r in bridge.calls] if bridge else []
            )
            try:
                result["artifacts"] = artifacts.save_artifacts(
                    {
                        **result,
                        "artifacts": [
                            a
                            for a in result.get("artifacts", [])
                            if a["path"] in result.get("updated_files", [])
                        ],
                    },
                    saved,
                    task_id=_current_task_id_var.get(),
                    inputs=request["inputs"],
                )
                for stream in ("stdout", "stderr"):
                    log = saved / f"{stream}.log"
                    if not log.is_file():
                        continue
                    content = log.read_bytes()
                    metadata = result.setdefault("streams", {}).setdefault(stream, {})
                    metadata["total_chars"] = len(content.decode("utf-8", errors="replace"))
                    ref = artifacts.save(
                        content,
                        source=f"exec://{execution_id}/{stream}",
                        media_type="text/plain",
                        name=stream,
                        metadata={
                            "producer_task": _current_task_id_var.get(),
                            "execution_id": execution_id,
                            "input_refs": request["inputs"],
                            "evidence_eligible": False,
                            "kind": "execution_result",
                        },
                    )
                    metadata["page_url"] = artifacts.publish(ref)
                    if stream == "stdout":
                        result["result_ref"] = ref
                        result["page_url"] = metadata["page_url"]
                        if result["page_url"]:
                            result["read_result"] = {"tool": "open", "arguments": {"id_or_url": result["page_url"]}}
                if bridge and bridge.calls:
                    result["child_results"] = artifacts.save_child_results(
                        bridge.calls, saved, task_id=_current_task_id_var.get(),
                    )
            except (OSError, ValueError, KeyError) as exc:
                result["artifact_error"] = str(exc)
            _write_json(
                receipt, {"state": "complete", "request_hash": request_hash, "result": result}
            )
    return response(result)


def source_network_policy():
    from searchos.tools.simple_browser.session import get_source_controls

    controls = get_source_controls()
    return controls if controls.excluded_domains else None
