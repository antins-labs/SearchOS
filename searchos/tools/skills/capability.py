"""将 Access Skill 注册为宿主桥能力 skill.call。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from uuid import uuid4

from searchos.skills.runtime.paths import skill_workspace_dir
from searchos.tools.exec.workspace import write_json

logger = logging.getLogger(__name__)

OP = "skill.call"


def register() -> None:
    from searchos.tools.exec.bridge import register_capability

    register_capability(OP, skill_call)


async def skill_call(bridge, request: dict) -> dict:
    from searchos.tools.search_state import _current_agent_var, _source_scope_var

    if not _current_agent_var.get().startswith("search_agent"):
        raise ValueError("Access Skills are only available to Search Agents")
    if (_source_scope_var.get() or {}).get("mode") == "local":
        raise ValueError("Access Skills are unavailable in Local source mode")

    skill = request.get("skill")
    if not isinstance(skill, str) or not skill.strip():
        raise ValueError("skill name is required")
    skill = skill.strip()

    params = request.get("params")
    argv = request.get("argv")
    stdin = request.get("stdin", "")
    if params is not None and argv is not None:
        raise ValueError("provide exactly one of params or argv")
    if params is not None:
        if not isinstance(params, dict):
            raise ValueError("params must be a JSON object")
        argv = ["python", "scripts/run.py", "--params-file", "-"]
        stdin = json.dumps(params, ensure_ascii=False)
    elif argv is not None:
        if not isinstance(argv, list) or not argv:
            raise ValueError("argv must be a nonempty list of strings")
        if not isinstance(stdin, str):
            raise ValueError("stdin must be text")
    else:
        raise ValueError("provide params or argv")

    execution_id = "exec-" + uuid4().hex
    normalized = {
        "op": OP,
        "skill": skill,
        "argv": argv,
        "stdin": stdin,
        **({"params": params} if params is not None else {}),
    }
    result = {"execution_id": execution_id, "status": "cancelled", "started": False}

    async def execute():
        nonlocal result
        from searchos.tools.simple_browser.session import _get_browser
        from searchos.tools.skills.execution import _run_skill

        saved = skill_workspace_dir(bridge.root, "executions") / execution_id
        receipt = (
            skill_workspace_dir(bridge.root, "calls")
            / bridge.key
            / (hashlib.sha256(execution_id.encode()).hexdigest() + ".json")
        )
        try:
            remaining = bridge.deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("execution deadline reached")
            _, artifact = await _run_skill(
                skill, argv, execution_id,
                stdin=stdin, timeout_s=min(300, remaining),
                execution_id=execution_id, parent_execution_id=bridge.parent_id,
            )
            result = artifact["execution"]
        except asyncio.CancelledError:
            if (saved / "record.json").is_file():
                result = json.loads((saved / "record.json").read_text())
            elif receipt.is_file():
                result = json.loads(receipt.read_text()).get("result") or result
            raise
        finally:
            result.setdefault("execution_id", execution_id)
            result["parent_execution_id"] = bridge.parent_id
            write_json(saved / "parent.json", {"parent_execution_id": bridge.parent_id})

        for item in result.get("pages", []):
            page = _get_browser().get_page_by_url(item["url"])
            if (
                page is not None
                and item["url"].endswith("/stdout")
                and page.metadata.get("evidence_eligible")
            ):
                bridge.observations.append(
                    {
                        "page_url": page.url,
                        "source_urls": page.metadata.get("source_urls", []),
                        "page_id": _get_browser().page_ids.get(page.url, ""),
                    }
                )
        return result

    try:
        result = await bridge.invoke_gated(OP, execution_id, normalized, execute)
    except asyncio.CancelledError:
        result["status"] = "cancelled"
        raise
    except Exception as exc:
        result.update(status="failed", error=str(exc))
        raise
    finally:
        result.update(
            execution_id=execution_id,
            parent_execution_id=bridge.parent_id,
            op=OP,
            skill=skill,
            argv=argv,
            **({"params": params} if params is not None else {}),
        )
        bridge.calls.append(result)

    result = dict(result)
    saved = skill_workspace_dir(bridge.root, "executions") / execution_id
    for stream in ("stdout", "stderr"):
        path = saved / f"{stream}.log"
        if path.is_file() and path.stat().st_size <= 10_000_000:
            result[stream] = path.read_text(errors="replace")
    return {
        key: result[key]
        for key in ("status", "stdout", "stderr", "error", "exit_code")
        if key in result
    }
