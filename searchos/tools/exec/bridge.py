"""通用宿主能力桥：unix socket 传输、能力注册表与嵌套调用钩子。"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextvars import ContextVar, copy_context
from pathlib import Path

# 预算 middleware 注入子调用入口；录制钩子记录嵌套调用。
# gate: async (op, call_id, request, execute) -> result
# recorder: async (op, call_id, request, parent_id, invoke) -> result
host_call_gate: ContextVar = ContextVar("searchos_host_call_gate", default=None)
host_call_recorder: ContextVar = ContextVar("searchos_host_call_recorder", default=None)
logger = logging.getLogger(__name__)

_CAPABILITIES: dict[str, object] = {}


def register_capability(op: str, handler) -> None:
    """注册宿主能力；同名覆盖。handler 签名: async (bridge, request) -> dict。"""
    if not isinstance(op, str) or not op:
        raise ValueError("capability op must be a nonempty string")
    _CAPABILITIES[op] = handler


def registered_capabilities() -> tuple[str, ...]:
    return tuple(sorted(_CAPABILITIES))


class HostBridge:
    def __init__(self, root, key, parent_id, socket_path, deadline):
        self.root, self.key, self.parent_id = root, key, parent_id
        self.socket_path, self.deadline = socket_path, deadline
        self.token = secrets.token_urlsafe(32)
        self.server = None
        self.tasks = set()
        self.calls = []
        self.observations = []
        self.context = copy_context()

    @property
    def executions(self):
        """兼容旧字段名：子调用记录。"""
        return self.calls

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
                op = request.get("op")
                if not isinstance(op, str) or op not in _CAPABILITIES:
                    raise ValueError("unknown host capability")
                result = await _CAPABILITIES[op](self, request)
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
            logger.exception("Host bridge execution failed")
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

    async def invoke_gated(self, op: str, call_id: str, request: dict, execute):
        """能力在创建 call_id 后调用，以便预算与录制拿到稳定标识。"""
        gate = host_call_gate.get()

        async def invoke():
            return await gate(op, call_id, request, execute) if gate else await execute()

        recorder = host_call_recorder.get()
        if recorder:
            return await recorder(op, call_id, request, self.parent_id, invoke)
        return await invoke()
