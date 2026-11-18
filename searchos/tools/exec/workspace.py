"""任务工作区路径、回执写入与共享目录锁。"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from searchos.tools.search_state import (
    _current_agent_var,
    _current_task_id_var,
    _workspace_var,
)

WORK_LOCK_WAIT_TIMEOUT_S = 300.0


async def acquire_work_lock(lock) -> None:
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
        raise ValueError(
            "timed out waiting for this task's work directory; command was not started"
        ) from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def context() -> tuple[Path, str]:
    ws = _workspace_var.get()
    if ws is None:
        raise ValueError("skill execution requires a bound task workspace")
    identity = _current_task_id_var.get() or _current_agent_var.get()
    key = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return ws.path.resolve(), key
