"""Exercise batch tools, evidence intake, workers, and I/O concurrency limits."""

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from searchos.config.settings import settings
from searchos.harness.middleware.extraction.web_middleware import WebEvidenceMiddleware
from searchos.harness.middleware.models import TaskContext
from searchos.tools.simple_browser import batch
from searchos.tools.simple_browser.render import PageContents
from searchos.tools.simple_browser.search.base import SearchResult
from tests.test_simple_search import ANSWER, FACT, URL, call, run
from tests.test_simple_search import setup as setup  # noqa: F401


@pytest.fixture
def pages(monkeypatch):
    counts = {"active": 0, "peak": 0, "search": 0, "open": 0}

    async def operation(kind):
        counts[kind] += 1
        counts["active"] += 1
        counts["peak"] = max(counts["peak"], counts["active"])
        try:
            await asyncio.sleep(.01)
        finally:
            counts["active"] -= 1

    class Provider:
        async def search(self, query, max_results=5):
            await operation("search")
            return [SearchResult(url=URL, title="Official release", snippet=FACT)]

    async def fetch(url):
        await operation("open")
        return PageContents(
            url=url, title="Official release", urls={},
            text=FACT + " Original release information and supporting details. " * 10,
        )

    monkeypatch.setattr(batch, "get_provider", lambda: Provider())
    monkeypatch.setattr(batch, "_fetch_page", fetch)
    monkeypatch.setattr(batch, "_read_page_from_disk", lambda _: None)
    from searchos.tools.simple_browser import reset_browser_for_sub_agent

    reset_browser_for_sub_agent()
    return counts


@pytest.mark.asyncio
async def test_batch_shared_io_limit_and_deduplication(pages):
    results = await asyncio.gather(*(batch.explore_web.ainvoke({
        "name": "explore_web", "args": {"queries": [f"date-{i}", f"official-{i}"]},
        "id": f"q-{i}", "type": "tool_call",
    }) for i in range(2)))
    assert pages["peak"] == 2 and pages["active"] == 0
    assert pages["search"] == 4
    assert all(len(result.artifact["pages"]) == 1 for result in results)
    assert all(result.artifact["pages"][0]["source_url"] == URL for result in results)
    assert batch.batch_io_gate.snapshot()["active"] == 0


@pytest.mark.asyncio
async def test_batch_accepts_many_queries_without_silent_clipping(pages):
    await batch.explore_web.ainvoke({"queries": [f"need-{i}" for i in range(14)]})
    assert pages["search"] == 14
    assert pages["peak"] == 2 and pages["active"] == 0


@pytest.mark.asyncio
async def test_batch_page_failure_never_promotes_search_snippet(pages, monkeypatch):
    async def failed(url):
        raise TimeoutError("page unavailable")

    monkeypatch.setattr(batch, "_fetch_page", failed)
    result = await batch.explore_web.ainvoke({"name": "explore_web", "id": "fail",
        "type": "tool_call", "args": {"queries": ["release date"]}})
    assert result.artifact["pages"][0]["evidence_eligible"] is False
    assert FACT not in result.artifact["pages"][0]["content"]


@pytest.mark.asyncio
async def test_cancelled_batch_releases_active_and_waiting_io(pages, monkeypatch):
    started = asyncio.Event()
    active = 0

    class SlowProvider:
        async def search(self, query, max_results=5):
            nonlocal active
            active += 1
            if active == 2:
                started.set()
            try:
                await asyncio.Event().wait()
            finally:
                active -= 1

    monkeypatch.setattr(batch, "get_provider", lambda: SlowProvider())
    jobs = [asyncio.create_task(batch.explore_web.ainvoke({"queries": ["a", "b"]}))
            for _ in range(2)]
    await asyncio.wait_for(started.wait(), 1)
    for job in jobs:
        job.cancel()
    await asyncio.gather(*jobs, return_exceptions=True)
    assert active == 0
    assert batch.batch_io_gate.snapshot()["active"] == 0
    assert batch.batch_io_gate.snapshot()["waiting"] == 0


@pytest.mark.asyncio
async def test_batch_observations_keep_separate_original_sources():
    observed = []

    async def submit(observation, **kwargs):
        observed.append(observation)
        return SimpleNamespace(feedback="")

    context = TaskContext(agent_id="search", task_id="q1", task_text="check both facts")
    middleware = WebEvidenceMiddleware(SimpleNamespace(task=context, submit=submit))
    pages = [{"source_url": f"https://example.org/{i}", "evidence_eligible": True,
              "content": f"[Now viewing]\nURL: https://example.org/{i}\n\n" + FACT * 10}
             for i in range(2)]

    async def handler(_):
        return ToolMessage(content="Misleading aggregate snippet", tool_call_id="q1",
                           artifact={"pages": pages})

    await middleware.awrap_tool_call(
        SimpleNamespace(tool_call={"name": "explore_web"}), handler)
    assert {o.source_url for o in observed} == {p["source_url"] for p in pages}
    assert all(o.task_id == "q1" and "Misleading" not in o.content for o in observed)


@pytest.mark.asyncio
async def test_batch_simple_worker_reuses_explore_pipeline(setup, pages, monkeypatch):
    async def handler(count, messages):
        queries = ["Widget official release", "Widget date",
                   "Widget announcement", "Widget archive"]
        return (call("explore_web", {"queries": queries}) if count == 1
                else AIMessage(content=ANSWER))

    from searchos.agents.runtime import _ctx
    from searchos.harness.middleware import pipelines

    original = pipelines.explore_pipeline
    invocations = []

    def observed(*args, **kwargs):
        invocations.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(pipelines, "explore_pipeline", observed)
    workspace, model, extraction = setup(handler)
    monkeypatch.setattr(settings, "enable_explore", True)
    result = await run(workspace)
    assert not result.escalate, result.reason
    assert result.answer == ANSWER and extraction.calls
    assert set(model.tool_names) == {"explore_web", "open", "find", "escalate_to_research"}
    assert len(model.calls) == 2
    assert len(invocations) == 1 and invocations[0]["extraction_model"] is extraction
    info = next(iter(_ctx.agent_graphs.values()))
    assert info["agent_type"] == "explore_agent" and info["task_kind"] == "search"
    assert not workspace.load_state().pending_agent_summaries
    report = next(iter(_ctx.completed.values()))
    assert report.kind == "search" and report.task_ids and report.evidence_nodes_added
    assert any(o.source == URL for o in workspace.load_state().evidence_graph.observations)


@pytest.mark.asyncio
async def test_batch_reads_relevant_text_beyond_old_700_token_window(pages, monkeypatch):
    fact = "The announced launch date is 19 October 2026."

    async def fetch(url):
        return PageContents(url=url, title="Long official page", urls={},
                            text="Navigation and introductory text. " * 400 + "\n" + fact)

    monkeypatch.setattr(batch, "_fetch_page", fetch)
    result = await batch.explore_web.ainvoke({"name": "explore_web", "id": "long",
        "type": "tool_call", "args": {"queries": ["announcement"]}})
    assert fact in result.content
    assert fact in result.artifact["pages"][0]["content"]


@pytest.mark.asyncio
async def test_planning_explore_still_stashes_brief_and_original_pages(setup, pages, monkeypatch):
    from searchos.agents.orchestrator.lifecycle import _spawn_sub_agent
    from searchos.agents.runtime import _ctx
    from searchos.socm import FrontierTask

    async def handler(count, messages):
        return (call("explore_web", {"queries": ["Widget release source"]}) if count == 1
                else AIMessage(content="Planning brief: the official release page identifies the "
                               "source needed for the next retrieval task. " + URL))

    workspace, _, _ = setup(handler)
    monkeypatch.setattr(settings, "enable_explore", True)
    state = workspace.load_state()
    state.frontier.add(FrontierTask(id="plan", question="Locate an official release source",
                                    kind="explore", agent_type="explore_agent"))
    workspace.save_state(state)
    agent_id = await _spawn_sub_agent("explore_agent", "Locate the source", [], bind_task_id="plan")
    report = await _ctx.task_pool.pop(agent_id)
    assert report.kind == "explore"
    assert not _ctx.agent_graphs[agent_id]["extractions"]
    state = workspace.load_state()
    assert any(p["source_url"] == URL for p in state.pending_agent_summaries)
    assert any(p["source_url"].startswith("agent://") for p in state.pending_agent_summaries)
    assert not state.evidence_graph.task_bindings
