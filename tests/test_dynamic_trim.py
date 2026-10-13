import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from searchos.harness.middleware.context import DynamicTrimMiddleware
from searchos.harness.middleware.context.utils.messages import estimate_tokens


@dataclass(frozen=True)
class _ModelRequest:
    messages: list
    model: object


def test_worker_profile_reads_dynamic_trim_fraction_setting(monkeypatch) -> None:
    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "dynamic_trim_fraction", 0.73)

    from searchos.harness.middleware.extraction import TaskContext
    from searchos.harness.middleware.pipelines import writer_pipeline
    from searchos.harness.middleware.sensor.core.models import BudgetState
    from tests.middleware_utils import capture_pipeline

    assembly = capture_pipeline(
        monkeypatch,
        writer_pipeline,
        workspace=None,
        task=TaskContext("writer"),
        budget=BudgetState(),
    )
    middleware = next(m for m in assembly.middleware if isinstance(m, DynamicTrimMiddleware))
    assert middleware._max_tokens_fraction == 0.73


def test_dynamic_trim_preserves_initial_task_without_socm_updates() -> None:
    mw = DynamicTrimMiddleware(max_tokens=1_000)
    task = "Collect the requested World Bank indicators for every target country."
    messages = [HumanMessage(content=task)]
    for index in range(12):
        call_id = f"call-{index}"
        messages.extend(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "skill_data_worldbank_org",
                            "args": {"country": str(index)},
                            "id": call_id,
                            "type": "tool_call",
                        }
                    ],
                ),
                ToolMessage(content="x" * 2_000, tool_call_id=call_id),
            ]
        )

    request = _ModelRequest(
        messages=messages,
        model=SimpleNamespace(profile={"max_input_tokens": 100_000}),
    )
    seen: dict[str, list] = {}

    async def handler(req):
        seen["messages"] = req.messages
        return "ok"

    asyncio.run(mw.awrap_model_call(request, handler))

    trimmed = seen["messages"]
    assert trimmed
    assert trimmed[0].type == "human"
    assert trimmed[0].content == task
    assert estimate_tokens(trimmed) <= 1_000
    assert [message.type for message in trimmed[1:]] == ["ai", "tool"]
    assert trimmed[1].tool_calls[0]["id"] == trimmed[2].tool_call_id


def test_tool_schema_counts_toward_request_budget():
    from searchos.harness.middleware.context.utils.messages import request_overhead_tokens

    request = SimpleNamespace(
        system_message=None,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "x" * 4000,
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )
    assert request_overhead_tokens(request) > 1600


def test_trim_keeps_corrections_latest_injections_and_parallel_transactions():
    from searchos.harness.middleware.context.utils.messages import trim_with_task_anchor

    task = HumanMessage("original task")
    correction = HumanMessage("Only compare revenue")
    old = HumanMessage(
        "old state", additional_kwargs={"sf_kind": "socm_update", "sf_synthetic": True}
    )
    snapshot = HumanMessage(
        "current state", additional_kwargs={"sf_kind": "socm_update", "sf_synthetic": True}
    )
    old_call = AIMessage("", tool_calls=[{"id": "old", "name": "read", "args": {}}])
    current = AIMessage(
        "",
        tool_calls=[
            {"id": "a", "name": "read", "args": {}},
            {"id": "b", "name": "read", "args": {}},
        ],
    )
    messages = [
        task,
        old,
        old_call,
        ToolMessage("x" * 5000, tool_call_id="old"),
        correction,
        current,
        ToolMessage("A", tool_call_id="a"),
        ToolMessage("B", tool_call_id="b"),
        snapshot,
    ]
    trimmed = trim_with_task_anchor(messages, 250)
    assert task in trimmed and correction in trimmed and snapshot in trimmed
    assert old not in trimmed
    assert [m.tool_call_id for m in trimmed if m.type == "tool"] == ["a", "b"]
    assert current in trimmed
    assert estimate_tokens(trimmed) <= 250


def test_worker_pipeline_trims_after_context_injection(monkeypatch):
    from searchos.config.settings import settings
    from searchos.harness.middleware import BudgetState, SOCMContextMiddleware, TaskContext
    from searchos.harness.middleware.pipelines import writer_pipeline
    from tests.middleware_utils import capture_pipeline

    monkeypatch.setattr(settings, "enable_socm_projection", True)
    assembly = capture_pipeline(
        monkeypatch,
        writer_pipeline,
        workspace=None,
        task=TaskContext("writer"),
        budget=BudgetState(),
    )
    names = [type(m) for m in assembly.middleware]
    assert names.index(DynamicTrimMiddleware) > names.index(SOCMContextMiddleware)
