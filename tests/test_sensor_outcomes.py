"""结构化结果、任务归属、失败路线的行为回归。"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from searchos.harness.middleware import TaskContext
from searchos.harness.middleware.extraction import InMemoryEvidenceStore
from searchos.harness.middleware.sensor.core.loops import EmptyResultSensor, ReadingReminderSensor
from searchos.harness.middleware.sensor.core.models import ControlState
from searchos.harness.middleware.sensor.progress_middleware import (
    ReadingProgressMiddleware,
    ToolProgressMiddleware,
)
from searchos.harness.middleware.sensor.route_middleware import RetryRouteMiddleware
from searchos.harness.middleware.utils.messages import is_blocked
from searchos.socm import FrontierTask, SearchState
from searchos.socm.evidence import EvidenceNode, bind_task_evidence


@pytest.mark.asyncio
async def test_structured_status_wins_over_words_and_length():
    sensor = EmptyResultSensor(threshold=1)
    for text in ("42", "This paper discusses error correction. " * 10):
        assert (
            await sensor.check(
                "open", ToolMessage(content=text, status="success", tool_call_id="x")
            )
            is None
        )
    signal = await sensor.check(
        "open", ToolMessage(content="Connection timed out. " * 10, status="error", tool_call_id="x")
    )
    assert signal["strategy_switch"]
    assert (await sensor.check("search", {"status": "ok", "results": []}))["strategy_switch"]


@pytest.mark.asyncio
async def test_failed_open_does_not_count_as_reading():
    sensor = ReadingReminderSensor(threshold=2)
    await sensor.check("search", "results")
    await sensor.check("open", ToolMessage(content="HTTP 503", status="error", tool_call_id="x"))
    assert await sensor.check("search", "results")


def test_reading_identity_uses_source_window_and_ignores_rendered_headers():
    reading = ReadingProgressMiddleware(set())
    for title in ("A", "B"):
        reading.observe(
            "open",
            ToolMessage(
                content=title,
                tool_call_id=title,
                artifact={
                    "page_source": {
                        "source_url": "https://example.org/a",
                        "viewport": {"start_line": 0, "end_line_exclusive": 20},
                    }
                },
            ),
        )
    assert len(reading.sources) == 1
    reading.observe(
        "open",
        ToolMessage(
            content="next",
            tool_call_id="c",
            artifact={
                "page_source": {
                    "source_url": "https://example.org/a",
                    "viewport": {"start_line": 20, "end_line_exclusive": 40},
                }
            },
        ),
    )
    assert len(reading.sources) == 2
    reading.observe(
        "local_open",
        ToolMessage(
            content="blocked",
            status="error",
            tool_call_id="d",
            artifact={
                "local_source_metadata": {
                    "ref_id": "local://doc",
                    "text_range": {"start": 0, "end": 10},
                },
            },
        ),
    )
    assert len(reading.sources) == 2


def workspace():
    state = SearchState()
    state.frontier.add(FrontierTask(id="own", question="own", assigned_agent_id="a"))
    state.frontier.add(FrontierTask(id="sibling", question="other", assigned_agent_id="b"))
    return InMemoryEvidenceStore(state)


@pytest.mark.asyncio
async def test_sibling_fact_does_not_reset_worker_progress_but_own_binding_does():
    ws = workspace()
    guard = ToolProgressMiddleware(
        ControlState(), limit=2, workspace=ws, task=TaskContext(agent_id="a", task_id="own")
    )
    request = SimpleNamespace(tool_call={"id": "x", "name": "open", "args": {}})

    async def sibling(_):
        ws.state.evidence_graph.add_node(
            EvidenceNode(id="e", finding="42", source="https://example.org")
        )
        bind_task_evidence(ws.state, "sibling", ["e"])
        return "source"

    await guard.awrap_tool_call(request, sibling)
    assert guard.empty_calls == 1

    async def own(_):
        bind_task_evidence(ws.state, "own", ["e"])
        return "source"

    await guard.awrap_tool_call(request, own)
    assert guard.empty_calls == 0
    assert not guard.control.stopped


@pytest.mark.asyncio
async def test_empty_route_blocks_exact_retry_but_allows_other_pages_windows_and_methods():
    ws = workspace()
    first = RetryRouteMiddleware(ws, agent_id="a")
    args = {"id_or_url": "https://example.org/report", "loc": 0}

    def req(name, args):
        return SimpleNamespace(tool_call={"id": "x", "name": name, "args": args})

    async def empty(_):
        return ToolMessage(
            content="No results", tool_call_id="x", artifact={"outcome": {"status": "empty"}}
        )

    await first.awrap_tool_call(req("open", args), empty)
    # Persistence and worker reassignment must preserve fine-grained outcomes.
    ws = InMemoryEvidenceStore(SearchState.model_validate_json(ws.state.model_dump_json()))
    ws.state.frontier.questions[0].assigned_agent_id = "c"
    retry = RetryRouteMiddleware(ws, agent_id="c")
    calls = []

    async def valid(request):
        calls.append(request.tool_call)
        return ToolMessage(content="42", tool_call_id="x")

    assert is_blocked(await retry.awrap_tool_call(req("open", args), valid))
    for name, other in (
        ("open", {"id_or_url": "https://example.org/other", "loc": 0}),
        ("open", {**args, "loc": 20}),
        ("read_visual", args),
    ):
        assert not is_blocked(await retry.awrap_tool_call(req(name, other), valid))
    assert len(calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["success", "error"])
async def test_success_or_unclassified_transient_error_does_not_ban_exact_route(status):
    ws = workspace()
    req = SimpleNamespace(
        tool_call={"id": "x", "name": "open", "args": {"id_or_url": "https://example.org/a"}}
    )

    async def result(_):
        return ToolMessage(content="source or temporary failure", status=status, tool_call_id="x")

    await RetryRouteMiddleware(ws, agent_id="a").awrap_tool_call(req, result)
    ws.state.frontier.questions[0].assigned_agent_id = "c"
    assert not is_blocked(await RetryRouteMiddleware(ws, agent_id="c").awrap_tool_call(req, result))


@pytest.mark.asyncio
async def test_default_tool_message_status_does_not_hide_legacy_error():
    sensor = EmptyResultSensor(threshold=1)
    assert await sensor.check("open", ToolMessage(content="Error: timeout", tool_call_id="x"))
    assert (
        await sensor.check(
            "open",
            ToolMessage(content="Error correction is useful", tool_call_id="x", status="success"),
        )
        is None
    )
