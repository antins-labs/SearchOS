"""追问队列与在模型边界插入 user 回合（打断未完成生成）。"""

from __future__ import annotations

import asyncio
import queue
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal
from uuid import uuid4

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_core.messages import HumanMessage

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


SteerQueue = SteeringQueue


def steering_pending(inbox: SteerQueue | None, *, immediate_only: bool = False) -> bool:
    return inbox is not None and inbox.has_pending(immediate_only=immediate_only)


def drain_steering(
    inbox: SteerQueue | None, *, immediate_only: bool = False,
) -> list[SteeringMessage]:
    if inbox is None:
        return []
    return inbox.drain(immediate_only=immediate_only)


async def wait_for_steering(inbox: SteerQueue, *, immediate_only: bool = False) -> None:
    await inbox.wait(immediate_only=immediate_only)


def take_follow_ups(
    inbox: SteerQueue | None,
    *,
    immediate_only: bool = False,
    delivered: list[str] | None = None,
    on_delivery=None,
    trajectory_logger=None,
) -> list[HumanMessage]:
    """Consume pending follow-ups as HumanMessages for the current thread."""
    messages = []
    for item in drain_steering(inbox, immediate_only=immediate_only):
        if delivered is not None:
            delivered.append(item.text)
        message = HumanMessage(
            content=item.text,
            id=f"steer-{item.id}",
            additional_kwargs={
                "sf_steer_id": item.id,
                "sf_steer_mode": item.mode,
                "sf_steer_text": item.text,
            },
        )
        messages.append(message)
        if on_delivery is not None:
            on_delivery(message)
        if trajectory_logger is not None:
            trajectory_logger._append_raw({
                "type": "harness",
                "kind": "steer_injected",
                "text": item.text,
                "message_id": item.id,
                "mode": item.mode,
            })
    return messages


class FollowUpTurns(AgentMiddleware):
    """在模型边界把追问插入为同会话的 user 回合。"""

    def __init__(self, inbox, *, trajectory_logger=None):
        self.inbox = inbox
        self.trajectory_logger = trajectory_logger
        self.delivered: list[str] = []
        self.on_delivery = None

    def take_messages(self, *, immediate_only=False):
        return take_follow_ups(
            self.inbox,
            immediate_only=immediate_only,
            delivered=self.delivered,
            on_delivery=self.on_delivery,
            trajectory_logger=self.trajectory_logger,
        )

    async def abefore_model(self, state, runtime):
        # LangGraph arrives here only after every parallel ToolMessage is saved.
        messages = self.take_messages()
        return {"messages": messages} if messages else None

    async def awrap_model_call(self, request, handler):
        injected = []
        while True:
            call = asyncio.create_task(handler(request))
            try:
                while True:
                    wake = asyncio.create_task(wait_for_steering(self.inbox, immediate_only=True))
                    try:
                        await asyncio.wait([call, wake], return_when=asyncio.FIRST_COMPLETED)
                        # A completed response owns its tool calls: let them execute.
                        if call.done():
                            response = await call
                            return replace(response, result=[*injected, *response.result])
                        messages = self.take_messages(immediate_only=True)
                        # A queued message can be deleted before this wake is handled.
                        if not messages:
                            continue
                        call.cancel()
                        await asyncio.gather(call, return_exceptions=True)
                        injected.extend(messages)
                        request = replace(request, messages=[*request.messages, *messages])
                        break
                    finally:
                        wake.cancel()
                        await asyncio.gather(wake, return_exceptions=True)
            finally:
                call.cancel()
                await asyncio.gather(call, return_exceptions=True)

    @hook_config(can_jump_to=["model"])
    async def aafter_model(self, state, runtime):
        # A queued follow-up must not be lost when generation ends without tools.
        if not getattr(state["messages"][-1], "tool_calls", None):
            messages = self.take_messages()
            if messages:
                return {"messages": messages, "jump_to": "model"}


def follow_up_turns(inbox, *, trajectory_logger=None) -> FollowUpTurns:
    return FollowUpTurns(inbox, trajectory_logger=trajectory_logger)


def find_follow_up_turns(middleware: Any) -> FollowUpTurns | None:
    return next((item for item in middleware if isinstance(item, FollowUpTurns)), None)
