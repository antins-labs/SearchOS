"""本地检索保留原文历史，其他 Agent 遵循全局压缩开关。"""

from dataclasses import dataclass

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from searchos.config.settings import settings
from searchos.harness.middleware.context.tool_history_middleware import ToolHistoryMiddleware
from searchos.harness.middleware.sensor.core.models import BudgetState
from searchos.harness.middleware.extraction import TaskContext
from searchos.harness.middleware.pipelines import local_search_pipeline, web_search_pipeline
from tests.middleware_utils import capture_pipeline


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize(
    "worker",
    [
        "local_search_agent",
        "local_search_agent_2",
        "orchestrator",
        "search_agent_2",
    ],
)
async def test_model_receives_history_for_worker(monkeypatch, enabled, worker):
    monkeypatch.setattr(settings, "compress_old_tool_results", enabled)

    @dataclass
    class Request:
        messages: list
        system_message: object = None

    messages = [
        ToolMessage(
            content=f"[LOCAL_SOURCE] window {i}\n" + "source text " * 50,
            tool_call_id=f"call-{i}",
        )
        for i in range(5)
    ]
    captured = []

    async def handler(request):
        captured.extend(request.messages)
        return AIMessage(content="done")

    pipeline = local_search_pipeline if worker.startswith("local_search_agent") else web_search_pipeline
    assembly = capture_pipeline(
        monkeypatch, pipeline,
        workspace=None,
        task=TaskContext(worker),
        budget=BudgetState(),
    )
    history = next(
        (mw for mw in assembly.middleware if isinstance(mw, ToolHistoryMiddleware)), None
    )
    if history:
        await history.awrap_model_call(Request(messages), handler)
    else:
        await handler(Request(messages))
    should_compress = enabled and not worker.startswith("local_search_agent")
    assert (captured[0].content != messages[0].content) == should_compress
    assert [m.content for m in captured[-3:]] == [m.content for m in messages[-3:]]
    if not should_compress:
        assert [m.content for m in captured] == [m.content for m in messages]
    assert messages[0].content.startswith("[LOCAL_SOURCE]")
