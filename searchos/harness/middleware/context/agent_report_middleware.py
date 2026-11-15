"""在完整工具批次之后交付报告；空闲时由任务完成或用户追问唤醒模型。"""

import json

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_core.messages import HumanMessage

from searchos.agents.runtime import _ctx, _scheduler
from searchos.harness.middleware.utils.messages import blocked_result
from searchos.harness.steering import steering_pending
from searchos.tools.tasks.reports import collect_agent_reports, report_wait_limit


class AgentReportMiddleware(AgentMiddleware):
    def __init__(self, pool, budget, control, on_reports=None):
        self.pool = pool
        self.budget = budget
        self.control = control
        self.on_reports = on_reports
        self.needs_tick = False

    def remaining_wait(self):
        if self.budget.max_time_s:
            return max(0, self.budget.max_time_s - self.budget.elapsed_s_live)
        return None

    async def awrap_tool_call(self, request, handler):
        if request.tool_call["name"] != "check_agents":
            return await handler(request)
        calls = request.state["messages"][-1].tool_calls
        first = next(call for call in calls if call["name"] == "check_agents")
        if first["id"] != request.tool_call["id"]:
            return blocked_result(request, "This batch already has a check_agents call. Read its result.")
        token = report_wait_limit.set(self.remaining_wait())
        try:
            return await handler(request)
        finally:
            report_wait_limit.reset(token)

    async def abefore_model(self, state, runtime):
        if self.control.forced or self.budget.fully_exhausted:
            return
        messages = state["messages"]
        last = messages[-1]
        if last.type == "human" and last.name == "agent_reports":
            return
        for result in reversed(messages):
            if result.type != "tool":
                break
            if result.name != "check_agents":
                continue
            try:
                receipt, _ = json.JSONDecoder().raw_decode(str(result.content))
            except ValueError:
                continue
            if isinstance(receipt, dict) and isinstance(receipt.get("reports"), list):
                # 本轮先处理显式等待的结果，包括超时；下一份报告留给下一轮。
                if receipt["reports"]:
                    await self.report_received(receipt)
                return
        if _ctx.report_inbox or any(task.done() for task in self.pool.values()):
            return await self.receive(wait=False)

    async def receive(self, wait):
        batch = await collect_agent_reports(timeout=self.remaining_wait() if wait else 0, immediate_only=False)
        if batch["reports"]:
            await self.report_received(batch)
            return {"messages": [HumanMessage(
                name="agent_reports", content=json.dumps(batch, ensure_ascii=False),
                additional_kwargs={"sf_synthetic": True},
            )]}

    async def report_received(self, batch):
        self.needs_tick = True
        if self.on_reports:
            await self.on_reports("agent_reports", batch)

    @hook_config(can_jump_to=["model"])
    async def aafter_model(self, state, runtime):
        if self.control.forced:
            return
        # 先将报告交给模型；处理完后再为已释放的槽位补派任务。
        if self.needs_tick and not _ctx.report_inbox:
            self.needs_tick = False
            if not self.budget.fully_exhausted and not steering_pending(_ctx.steer_queue, immediate_only=False):
                await _scheduler().tick()
        if getattr(state["messages"][-1], "tool_calls", None):
            return
        if not self.pool and not _ctx.report_inbox:
            if not any(q.status == "pending" for q in _ctx.workspace.load_state().frontier.questions):
                return
        if self.budget.fully_exhausted:
            return {"jump_to": "model"}
        while True:
            update = await self.receive(True)
            if update or steering_pending(_ctx.steer_queue) or self.budget.fully_exhausted:
                return {**(update or {}), "jump_to": "model"}
            if self.control.forced or not (self.pool or _ctx.report_inbox):
                return
