"""将 Exec 子进程的技能调用转交给当前任务的工具执行层。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from contextvars import ContextVar, copy_context
from pathlib import Path
from uuid import uuid4

from searchos.skills.runtime.paths import skill_workspace_dir
from searchos.tools.skills.execution import _write_json

# 预算 middleware 注入子调用入口，直接工具测试可独立装配执行后端。
nested_execution: ContextVar = ContextVar("searchos_nested_execution", default=None)
nested_recording: ContextVar = ContextVar("searchos_nested_recording", default=None)
logger = logging.getLogger(__name__)


class SkillBridge:
    def __init__(self, root, key, parent_id, socket_path, deadline):
        self.root, self.key, self.parent_id = root, key, parent_id
        self.socket_path, self.deadline = socket_path, deadline
        self.token = secrets.token_urlsafe(32)
        self.server = None
        self.tasks = set()
        self.executions = []
        self.observations = []
        self.context = copy_context()

    async def __aenter__(self):
        def connected(reader, writer):
            task = asyncio.create_task(self.handle(reader, writer), context=self.context.copy())
            self.tasks.add(task)

            def finished(done):
                self.tasks.discard(done)
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(finished)

        self.server = await asyncio.start_unix_server(
            connected, path=self.socket_path, limit=150_000
        )
        Path(self.socket_path).chmod(0o600)
        return self

    async def __aexit__(self, *_):
        self.server.close()
        await self.server.wait_closed()
        pending = list(self.tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        Path(self.socket_path).unlink(missing_ok=True)

    async def handle(self, reader, writer):
        try:
            async with asyncio.timeout_at(self.deadline):
                request = json.loads(await reader.readline())
                if not secrets.compare_digest(str(request.pop("token", "")), self.token):
                    raise ValueError("invalid task capability")
                if request.get("op") == "run":
                    result = await self.run(request)
                else:
                    raise ValueError("unknown CLI operation")
        except (ValueError, OSError, TypeError, KeyError, TimeoutError) as exc:
            result = {
                "status": "blocked",
                "error": str(exc) or "execution deadline reached",
                "exit_code": 1,
            }
        except asyncio.CancelledError:
            writer.close()
            raise
        except Exception:
            logger.exception("SearchAnything host execution failed")
            result = {
                "status": "failed",
                "error": "host execution failed; inspect execution logs",
                "exit_code": 1,
            }
        try:
            writer.write(json.dumps(result, ensure_ascii=False).encode() + b"\n")
            await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    async def run(self, request):
        from searchos.tools.search_state import _current_agent_var, _source_scope_var

        if not _current_agent_var.get().startswith("search_agent"):
            raise ValueError("Access Skills are only available to Search Agents")
        if (_source_scope_var.get() or {}).get("mode") == "local":
            raise ValueError("Access Skills are unavailable in Local source mode")
        execution_id = "exec-" + uuid4().hex
        result = {"execution_id": execution_id, "status": "cancelled", "started": False}

        async def execute():
            nonlocal result
            from searchos.tools.simple_browser.session import _get_browser
            from searchos.tools.skills.execution import _run_skill

            saved = skill_workspace_dir(self.root, "executions") / execution_id
            receipt = (
                skill_workspace_dir(self.root, "calls")
                / self.key
                / (hashlib.sha256(execution_id.encode()).hexdigest() + ".json")
            )
            try:
                remaining = self.deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError("execution deadline reached")
                _, artifact = await _run_skill(
                    request["skill"], request["argv"], execution_id,
                    stdin=request.get("stdin", ""), timeout_s=min(300, remaining),
                    execution_id=execution_id, parent_execution_id=self.parent_id,
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
                result["parent_execution_id"] = self.parent_id
                _write_json(saved / "parent.json", {"parent_execution_id": self.parent_id})

            for item in result.get("pages", []):
                page = _get_browser().get_page_by_url(item["url"])
                if (
                    page is not None
                    and item["url"].endswith("/stdout")
                    and page.metadata.get("evidence_eligible")
                ):
                    self.observations.append(
                        {
                            "page_url": page.url,
                            "source_urls": page.metadata.get("source_urls", []),
                            "page_id": _get_browser().page_ids.get(page.url, ""),
                        }
                    )
            return result

        callback = nested_execution.get()

        async def invoke():
            return await callback(execution_id, request, execute) if callback else await execute()

        recorder = nested_recording.get()
        try:
            result = (
                await recorder(execution_id, request, self.parent_id, invoke)
                if recorder
                else await invoke()
            )
        except asyncio.CancelledError:
            result["status"] = "cancelled"
            raise
        except Exception as exc:
            result.update(status="failed", error=str(exc))
            raise
        finally:
            result.update(execution_id=execution_id, parent_execution_id=self.parent_id,
                          skill=request["skill"], argv=request["argv"])
            self.executions.append(result)
        result = dict(result)
        saved = skill_workspace_dir(self.root, "executions") / execution_id
        for stream in ("stdout", "stderr"):
            path = saved / f"{stream}.log"
            if path.is_file() and path.stat().st_size <= 10_000_000:
                result[stream] = path.read_text(errors="replace")
        return {
            key: result[key]
            for key in ("status", "stdout", "stderr", "error", "exit_code")
            if key in result
        }
