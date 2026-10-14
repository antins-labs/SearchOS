"""Web/TUI 共用的追问队列：入队唤醒等待，消费仍由主循环负责。"""

from __future__ import annotations

import asyncio
import queue
from dataclasses import asdict, dataclass, field, replace
from typing import Literal
from uuid import uuid4

SteeringMode = Literal["immediate", "after_tool"]


@dataclass(frozen=True)
class SteeringMessage:
    text: str
    mode: SteeringMode = "immediate"
    id: str = field(default_factory=lambda: uuid4().hex)


def _immediate(item: str | SteeringMessage) -> bool:
    return isinstance(item, str) or item.mode == "immediate"


def _wake(waiter: asyncio.Future[None]) -> None:
    if not waiter.done():
        waiter.set_result(None)


class SteeringQueue(queue.Queue[str | SteeringMessage]):
    """支持 TUI 跨线程投递，不在等待通知时取走用户消息。"""

    def __init__(self) -> None:
        super().__init__()
        self._waiters: set[tuple[asyncio.AbstractEventLoop, asyncio.Future[None], bool]] = set()
        self._receipts: dict[str, dict] = {}
        self._revision = 0

    def _put(self, item: str | SteeringMessage) -> None:
        # Queue holds its mutex through insertion and waiter notification.
        super()._put(item)
        if isinstance(item, SteeringMessage):
            self._receipts[item.id] = {**asdict(item), "status": "queued"}
            self._revision += 1
        self._notify_waiters(item)

    def _notify_waiters(self, item: str | SteeringMessage) -> None:
        for loop, waiter, immediate_only in self._waiters:
            if immediate_only and not _immediate(item):
                continue
            try:
                loop.call_soon_threadsafe(_wake, waiter)
            except RuntimeError:
                # A closed UI/session loop must not prevent queue insertion.
                pass

    def snapshot(self) -> dict:
        with self.mutex:
            return {
                "revision": self._revision,
                "messages": [dict(receipt) for receipt in self._receipts.values()],
            }

    def promote(self, message_id: str) -> bool:
        """就地改为立即引导；已经消费的消息不能再次投递。"""
        with self.mutex:
            for index, item in enumerate(self.queue):
                if isinstance(item, SteeringMessage) and item.id == message_id:
                    immediate = replace(item, mode="immediate")
                    self.queue[index] = immediate
                    self._receipts[item.id]["mode"] = "immediate"
                    self._revision += 1
                    self._notify_waiters(immediate)
                    return True
        return False

    def remove(self, message_id: str) -> bool:
        """只能删除尚未消费的追问。"""
        with self.not_full:
            for index, item in enumerate(self.queue):
                if isinstance(item, SteeringMessage) and item.id == message_id:
                    del self.queue[index]
                    self._receipts[item.id]["status"] = "cancelled"
                    self._revision += 1
                    self.unfinished_tasks -= 1
                    if not self.unfinished_tasks:
                        self.all_tasks_done.notify_all()
                    self.not_full.notify_all()
                    return True
        return False

    def has_pending(self, *, immediate_only: bool = False) -> bool:
        with self.mutex:
            if immediate_only:
                return any(_immediate(item) for item in self.queue)
            return bool(self.queue)

    def drain(self, *, immediate_only: bool = False) -> list[SteeringMessage]:
        """原子消费可投递消息；延后消息保持顺序，立即引导可越过它们。"""
        items = []
        with self.not_full:
            for _ in range(self._qsize()):
                item = self._get()
                if immediate_only and not _immediate(item):
                    self.queue.append(item)
                else:
                    items.append(
                        item if isinstance(item, SteeringMessage) else SteeringMessage(item)
                    )
                    if isinstance(item, SteeringMessage):
                        self._receipts[item.id]["status"] = "delivered"
                        self._revision += 1
            if items:
                self.not_full.notify_all()
        return items

    async def wait(self, *, immediate_only: bool = False) -> None:
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        registration = (loop, waiter, immediate_only)
        with self.mutex:
            if any(_immediate(item) or not immediate_only for item in self.queue):
                return
            self._waiters.add(registration)
        try:
            await waiter
        finally:
            with self.mutex:
                self._waiters.discard(registration)


SteerQueue = SteeringQueue | asyncio.Queue[str] | queue.Queue[str]


def steering_pending(inbox: SteerQueue | None, *, immediate_only: bool = False) -> bool:
    if isinstance(inbox, SteeringQueue):
        return inbox.has_pending(immediate_only=immediate_only)
    return inbox is not None and not inbox.empty()


def drain_steering(
    inbox: SteerQueue | None, *, immediate_only: bool = False,
) -> list[SteeringMessage]:
    if isinstance(inbox, SteeringQueue):
        return inbox.drain(immediate_only=immediate_only)
    items = []
    if inbox is not None:
        while True:
            try:
                items.append(SteeringMessage(inbox.get_nowait()))
            except (asyncio.QueueEmpty, queue.Empty):
                break
    return items


async def wait_for_steering(inbox: SteerQueue, *, immediate_only: bool = False) -> None:
    if isinstance(inbox, SteeringQueue):
        await inbox.wait(immediate_only=immediate_only)
    else:
        # Compatibility for external callers supplying ordinary queues.
        # Never consume here: only the harness may inject at a safe boundary.
        while inbox.empty():
            await asyncio.sleep(0.05)
