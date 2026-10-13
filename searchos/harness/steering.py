"""Web/TUI 共用的追问队列：入队唤醒等待，消费仍由主循环负责。"""

from __future__ import annotations

import asyncio
import queue


def _wake(waiter: asyncio.Future[None]) -> None:
    if not waiter.done():
        waiter.set_result(None)


class SteeringQueue(queue.Queue[str]):
    """支持 TUI 跨线程投递，不在等待通知时取走用户消息。"""

    def __init__(self) -> None:
        super().__init__()
        self._waiters: set[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = set()

    def _put(self, item: str) -> None:
        # Queue holds its mutex through insertion and waiter notification.
        super()._put(item)
        for loop, waiter in self._waiters:
            try:
                loop.call_soon_threadsafe(_wake, waiter)
            except RuntimeError:
                # A closed UI/session loop must not prevent queue insertion.
                pass

    async def wait(self) -> None:
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        registration = (loop, waiter)
        with self.mutex:
            if self._qsize():
                return
            self._waiters.add(registration)
        try:
            await waiter
        finally:
            with self.mutex:
                self._waiters.discard(registration)


SteerQueue = asyncio.Queue[str] | queue.Queue[str]


async def wait_for_steering(inbox: SteerQueue) -> None:
    if isinstance(inbox, SteeringQueue):
        await inbox.wait()
    else:
        # Compatibility for external callers supplying ordinary queues.
        # Never consume here: only the harness may inject at a safe boundary.
        while inbox.empty():
            await asyncio.sleep(0.05)
