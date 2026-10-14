"""在模型边界消费追问；立即引导只撤销尚未完成的模型生成。"""

from __future__ import annotations

import asyncio
from dataclasses import replace

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_core.messages import HumanMessage

from searchos.harness.steering import drain_steering, wait_for_steering


class SteeringMiddleware(AgentMiddleware):
    def __init__(self, inbox, *, trajectory_logger=None):
        self.inbox = inbox
        self.trajectory_logger = trajectory_logger
        self.delivered: list[str] = []
        self.on_delivery = None

    def take_messages(self, *, immediate_only=False):
        messages = []
        for item in drain_steering(self.inbox, immediate_only=immediate_only):
            self.delivered.append(item.text)
            messages.append(HumanMessage(
                content=f"[用户追问 — 实时插入]\n{item.text}",
                id=f"steer-{item.id}",
                additional_kwargs={
                    "sf_steer_id": item.id, "sf_steer_mode": item.mode, "sf_steer_text": item.text,
                },
            ))
            if self.on_delivery is not None:
                self.on_delivery(messages[-1])
            if self.trajectory_logger is not None:
                self.trajectory_logger._append_raw({
                    "type": "harness", "kind": "steer_injected", "text": item.text,
                    "message_id": item.id, "mode": item.mode,
                })
        return messages

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
