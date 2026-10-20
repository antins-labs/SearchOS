"""Thread-safe admission control for callers sharing a bounded resource pool."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager


class ConcurrencyGate:
    """Share FIFO capacity across threads and event loops without leaking cancelled waits."""

    def __init__(self, limit: int) -> None:
        self._condition = threading.Condition()
        self._limit = max(1, int(limit))
        self._waiting: deque[object] = deque()
        self._active = self._peak = self._admitted = self._completed = 0
        self._wait_seconds = 0.0

    def set_limit(self, limit: int) -> None:
        with self._condition:
            self._limit = max(1, int(limit))
            self._condition.notify_all()

    def snapshot(self) -> dict[str, int | float]:
        """Return request counts and wait time for diagnostics."""
        with self._condition:
            return {
                "limit": self._limit,
                "active": self._active,
                "peak": self._peak,
                "waiting": len(self._waiting),
                "admitted": self._admitted,
                "completed": self._completed,
                "wait_seconds": self._wait_seconds,
            }

    def reset_metrics(self) -> None:
        """Reset metrics only when no requests are active or waiting."""
        with self._condition:
            if self._active or self._waiting:
                raise RuntimeError("Cannot reset concurrency metrics while requests are active")
            self._peak = self._admitted = self._completed = 0
            self._wait_seconds = 0.0

    def _enqueue(self) -> tuple[object, float]:
        ticket = object()
        with self._condition:
            self._waiting.append(ticket)
        return ticket, time.monotonic()

    def _try_acquire(self, ticket: object, started: float) -> bool:
        with self._condition:
            if self._active >= self._limit or self._waiting[0] is not ticket:
                return False
            self._waiting.popleft()
            self._active += 1
            self._peak = max(self._peak, self._active)
            self._admitted += 1
            self._wait_seconds += time.monotonic() - started
            self._condition.notify_all()
            return True

    def _cancel_wait(self, ticket: object) -> None:
        with self._condition:
            self._waiting.remove(ticket)
            self._condition.notify_all()

    def acquire(self) -> None:
        ticket, started = self._enqueue()
        try:
            with self._condition:
                while not self._try_acquire(ticket, started):
                    self._condition.wait()
        except BaseException:
            self._cancel_wait(ticket)
            raise

    async def aacquire(self) -> None:
        ticket, started = self._enqueue()
        try:
            while not self._try_acquire(ticket, started):
                # 不绑定某个事件循环，也不让取消后的线程继续领取额度。
                await asyncio.sleep(0.01)
        except BaseException:
            self._cancel_wait(ticket)
            raise

    def release(self) -> None:
        with self._condition:
            if self._active <= 0:
                raise RuntimeError("Concurrency slot released without acquisition")
            self._active -= 1
            self._completed += 1
            self._condition.notify_all()

    @contextmanager
    def slot(self) -> Iterator[None]:
        self.acquire()
        try:
            yield
        finally:
            self.release()

    @asynccontextmanager
    async def aslot(self) -> AsyncIterator[None]:
        await self.aacquire()
        try:
            yield
        finally:
            self.release()
