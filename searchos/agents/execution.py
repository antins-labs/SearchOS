"""图入口为已装载组件管理运行资源，不选择业务功能。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import aclosing, asynccontextmanager
from dataclasses import replace
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableConfig

from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.utils.messages import (
    blocked_result,
    call_with_context,
    extract_tool_name,
    unwrap_ai_message,
)


class _BeforeModel(AgentMiddleware):
    """状态读取前等待已启动的抽取；未装载资源时不安装此 hook。"""

    def __init__(self, resources: Sequence[Any]) -> None:
        self.resources = resources

    async def awrap_model_call(self, request: Any, handler: Callable) -> Any:
        for resource in self.resources:
            await resource.drain_before_model()
        return await handler(request)


def loaded_resources(middleware: Sequence[AgentMiddleware]) -> tuple[Any, ...]:
    resources: list[Any] = []
    seen: set[int] = set()
    for component in middleware:
        for resource in getattr(component, "run_resources", ()):
            if id(resource) not in seen:
                resources.append(resource)
                seen.add(id(resource))
    return tuple(resources)


@asynccontextmanager
async def _run_resources(resources: Sequence[Any], timeout: float) -> AsyncIterator[None]:
    error: BaseException | None = None
    try:
        yield
    except BaseException as exc:
        error = exc
        raise
    finally:

        async def finish():
            # 一个资源失败不能跳过其他资源的收尾。
            results = await asyncio.gather(
                *(resource.finalize(timeout=timeout) for resource in resources),
                return_exceptions=True,
            )
            failures = [result for result in results if isinstance(result, BaseException)]
            if failures:
                first = failures[0]
                for failure in failures[1:]:
                    first.add_note(f"Additional resource finalization failure: {failure}")
                raise first

        cleanup = asyncio.create_task(finish())
        cancelled: asyncio.CancelledError | None = None
        # 即使清理期间重复取消，也等待收尾任务结束。
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError as exc:
                cancelled = exc
            except BaseException:
                break
        try:
            cleanup.result()
        except BaseException as exc:
            if error is not None:
                error.add_note(f"Resource finalization failed: {exc}")
            elif cancelled is not None:
                cancelled.add_note(f"Resource finalization failed: {exc}")
            else:
                raise
        if cancelled is not None and error is None:
            raise cancelled


class _ManagedGraph(Runnable[Any, Any]):
    """保持 Runnable 调用与配置组合；所有运行途径经过相同的资源收尾。"""

    def __init__(self, graph: Any, resources: Sequence[Any], timeout: float) -> None:
        self.graph = graph
        self.resources = tuple(resources)
        self.timeout = timeout

    def __getattr__(self, name: str) -> Any:
        return getattr(self.graph, name)

    def get_graph(self, config: RunnableConfig | None = None, *, xray=False):
        return self.graph.get_graph(config, xray=xray)

    async def aget_graph(self, config: RunnableConfig | None = None, *, xray=False):
        return await self.graph.aget_graph(config, xray=xray)

    def get_input_schema(self, config: RunnableConfig | None = None):
        return self.graph.get_input_schema(config)

    def get_output_schema(self, config: RunnableConfig | None = None):
        return self.graph.get_output_schema(config)

    async def ainvoke(self, input: Any, config: RunnableConfig | None = None, **kwargs) -> Any:
        async with _run_resources(self.resources, self.timeout):
            return await self.graph.ainvoke(input, config, **kwargs)

    async def astream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs,
    ) -> AsyncIterator[Any]:
        async with _run_resources(self.resources, self.timeout):
            async with aclosing(self.graph.astream(input, config, **kwargs)) as stream:
                async for item in stream:
                    yield item

    def invoke(self, input: Any, config: RunnableConfig | None = None, **kwargs) -> Any:
        with asyncio.Runner() as runner:
            return runner.run(self.ainvoke(input, config, **kwargs))

    def stream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs,
    ) -> Iterator[Any]:
        with asyncio.Runner() as runner:
            stream = self.astream(input, config, **kwargs)
            try:
                while True:
                    try:
                        item = runner.run(anext(stream))
                    except StopAsyncIteration:
                        break
                    yield item
            finally:
                runner.run(stream.aclose())


def bind_controls(middleware: Sequence[AgentMiddleware], control=None) -> ControlState:
    controls = {id(control): control} if control is not None else {}
    for component in middleware:
        state = getattr(component, "control", None)
        if state is not None:
            controls[id(state)] = state
    if len(controls) > 1:
        raise ValueError("One agent must share one ControlState across runtime and sensors")
    control = next(iter(controls.values()), None) or ControlState()
    for component in middleware:
        bind = getattr(component, "bind_control", None)
        if bind is not None:
            bind((control,))
    return control


class ControlExecutor:
    def __init__(
        self,
        control: ControlState,
        *,
        drain_tools: frozenset[str] = frozenset(),
        finish_without_tools: bool = True,
    ) -> None:
        self.control = control
        self.drain_tools = drain_tools
        self.finish_without_tools = finish_without_tools

    async def call_tool(self, request: Any, handler: Callable) -> Any:
        name = extract_tool_name(request)
        if self.control.blocks(name) or (self.control.forced and name not in self.drain_tools):
            return blocked_result(
                request,
                (
                    f"[Harness] Tool '{name}' is hard-blocked ({self.control.reason}). "
                    f"Only drain tools remain: {', '.join(sorted(self.drain_tools)) or 'none'}. "
                    "Wrap up with supported findings and unresolved limitations."
                ),
            )
        return await handler(request)

    async def call_model(self, request: Any, handler: Callable) -> Any:
        signals = list(self.control.messages)
        self.control.messages.clear()
        if self.control.strategy_switch:
            signals.append(
                "[Harness STRATEGY_SWITCH] Change queries, sources or retrieval strategy."
            )
            self.control.strategy_switch = False
        if self.control.forced:
            signals.append(
                self.control.stop_message
                or (
                    f"HARD STOP — {self.control.reason}\n"
                    f"Tools still allowed: {', '.join(sorted(self.drain_tools)) or 'none'}. "
                    "Summarize supported findings and gaps; do not resume retrieval."
                )
            )
        if signals:
            response = await call_with_context(
                request, handler, content="\n\n".join(signals), kind="harness_control",
            )
        else:
            response = await handler(request)
        message = unwrap_ai_message(response)
        calls = getattr(message, "tool_calls", None) or (
            getattr(message, "additional_kwargs", {}) or {}
        ).get("tool_calls")
        if self.control.forced and self.finish_without_tools and calls:
            content = (
                f"Search stopped by harness ({self.control.reason}). "
                "No further tool calls were executed. "
                "Findings are partial; unresolved targets remain limitations."
            )
            if self.control.context_snapshot:
                content += "\n\n" + self.control.context_snapshot
            if isinstance(message, AIMessage):
                extra = dict(message.additional_kwargs)
                extra.pop("tool_calls", None)
                extra.pop("function_call", None)
                terminal = message.model_copy(
                    update={
                        "content": content,
                        "tool_calls": [],
                        "invalid_tool_calls": [],
                        "additional_kwargs": extra,
                    }
                )
            else:
                terminal = AIMessage(content=content)
            if hasattr(response, "result"):
                updates = [m for m in response.result if m.type not in {"ai", "tool"}]
                return replace(response, result=[*updates, terminal])
            return terminal
        return response


class _ExecutionHooks(AgentMiddleware):
    """框架接入层：执行控制信号及 agent 策略，不产生搜索停止条件。"""

    def __init__(
        self, executor: ControlExecutor, *, policy=None, image_fallback=True, recorder=None
    ):
        self.recorder = recorder
        self.executor = executor
        self.policy = policy
        self.image_fallback = image_fallback

    async def awrap_model_call(self, request, handler):
        from searchos.agents.model_call import call_model

        async def invoke_model(request):
            if self.recorder is not None:
                self.recorder.model_received(request)
            return await call_model(request, handler, image_fallback=self.image_fallback)

        async def invoke_policy(request):
            if self.policy is not None:
                return await self.policy.call_model(request, invoke_model)
            return await invoke_model(request)

        return await self.executor.call_model(request, invoke_policy)

    async def awrap_tool_call(self, request, handler):
        async def execute(request):
            if self.policy is not None and hasattr(self.policy, "call_tool"):
                return await self.policy.call_tool(request, handler)
            return await handler(request)

        return await self.executor.call_tool(request, execute)


class _RecordingHooks(AgentMiddleware):
    """把框架事件交给 session recorder；业务 middleware 无需持有它。"""

    def __init__(self, recorder):
        self.recorder = recorder

    async def awrap_model_call(self, request, handler):
        result = await handler(request)
        self.recorder.model_completed(result)
        return result

    async def awrap_tool_call(self, request, handler):
        started = self.recorder.tool_started(request)
        try:
            result = await handler(request)
        except asyncio.CancelledError as error:
            self.recorder.tool_failed(request, error, started, cancelled=True)
            raise
        except Exception as error:
            self.recorder.tool_failed(request, error, started)
            raise
        self.recorder.tool_completed(request, result, started)
        return result
