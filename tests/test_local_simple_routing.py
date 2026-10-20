"""Exercise local tools and extraction while preserving source permissions on handoff."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

from searchos.agents import runtime
from searchos.config.settings import settings
from searchos.harness.middleware.context.steering_middleware import SteeringMiddleware
from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
from searchos.harness.routing import SearchRoute, select_route
from searchos.harness.simple_search import run_simple_search
from searchos.harness.steering import SteeringQueue
from searchos.local.library import LocalLibraryService
from searchos.local.reader.references import build_ref_id
from searchos.socm import SearchState, WorkspaceManager
from searchos.tools import search_state
from tests.test_simple_search import OfflineModel, call

FACT = "Atlas allows exactly two concurrent jobs."


@pytest.mark.asyncio
async def test_local_source_is_a_permission_boundary_not_a_research_shortcut():
    choice = SearchRoute(path="simple", reason="One document fact",
                         evidence_obligations=["Read the stated concurrency limit"],
                         strategy=["simple"])
    model = SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(
        content=choice.model_dump_json())))
    state = SearchState(source_scope={"mode": "local", "documents": []})
    result = await select_route(model=model, query="How many jobs?", state=state)
    assert result.path == "simple"
    payload = json.loads(model.ainvoke.call_args.args[0][-1].content)
    assert payload == {"question": "How many jobs?", "source_mode": "local"}


@pytest.mark.asyncio
@pytest.mark.parametrize("upgrade", [False, True])
async def test_local_simple_reads_authorized_source_and_retains_evidence(
    tmp_path, monkeypatch, upgrade,
):
    for name in ("enable_skills", "enable_failure_memory", "enable_writer_agent"):
        monkeypatch.setattr(settings, name, False)
    monkeypatch.setattr(settings, "middleware_pipelines", {})
    service = LocalLibraryService(tmp_path / "library")
    library = service.create_library("Deployment rules")
    incoming = tmp_path / "incoming.md"
    incoming.write_text("# Deployment rules\n\n" + FACT)
    doc = await service.index_uploaded_file(library.library_id, incoming, "rules.md")
    record, block = service._verified_blocks(library.library_id, [doc["document_id"]])[0]
    ref = build_ref_id(library_id=library.library_id, document_id=record.document_id,
                       source_revision=record.source_revision, locators=list(block.source_locators))
    scope = {"mode": "local", "library_id": library.library_id,
             "index_root": library.index_root, "selection": "documents",
             "documents": [record.model_dump(mode="json")]}
    workspace = WorkspaceManager(tmp_path / "runs", "local-simple")
    workspace.create()
    workspace.save_state(SearchState(intent="How many jobs?", source_scope=scope,
                                    research_mode="findings"))
    search_state.set_workspace(workspace)
    scope_token = search_state._source_scope_var.set(scope)

    class Extraction:
        async def ainvoke(self, prompt):
            rows = ([{"id": "0", "supported": True}]
                    if "Verify whether each fact" in prompt else
                    [{"finding": FACT, "source_excerpt": FACT,
                      "relation": "supports", "source_urls": [ref]}])
            return SimpleNamespace(content=json.dumps(rows))

    async def handler(count, messages):
        if count == 1:
            return call("local_open", {"ref_id": ref})
        if upgrade and count == 2:
            await asyncio.sleep(.2)
            return call("escalate_to_research", {"reason": "Compare the other documents"}, number=2)
        return AIMessage(content=f"Two jobs. [Rules]({ref})")

    model = OfflineModel(handler=handler)
    runtime.set_orchestrator_context(workspace=workspace, model=model, sub_agent_model=model,
                                     extraction_model=Extraction())
    try:
        outcome = await run_simple_search(
            workspace=workspace, query="How many jobs?",
            evidence_obligations=["Read the stated concurrency limit"],
            remaining_time_s=.15 if upgrade else 10, steer_queue=SteeringQueue(),
        )
        assert outcome.escalate is upgrade, outcome.reason
        assert set(model.tool_names) == {
            "local_catalog", "local_open", "local_find", "escalate_to_research",
        }
        state = workspace.load_state()
        assert state.source_scope == scope
        task = state.frontier.questions[0]
        assert task.agent_type == "local_search_agent"
        assert task.status.value == ("cancelled" if upgrade else "completed")
        nodes = [node for node in state.evidence_graph.nodes if node.source == ref]
        assert nodes and nodes[0].source_excerpt == FACT
        assert any(binding.task_id == task.id for binding in state.evidence_graph.task_bindings)
        assert not runtime._ctx.task_pool
        graph = next(iter(runtime._ctx.agent_graphs.values()))["graph"]
        assert any(isinstance(item, SteeringMiddleware) for item in graph.middleware)
        budget = next(item.budget for item in graph.middleware
                      if isinstance(item, BudgetMiddleware))
        assert (budget.max_queries, budget.max_iterations, budget.max_time_s) == (
            15, 0, .15 if upgrade else 10,
        )
    finally:
        search_state._source_scope_var.reset(scope_token)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["simple", "research"])
async def test_local_session_completes_through_real_selected_pipeline(tmp_path, monkeypatch, path):
    from searchos.config import models
    from searchos.harness.session import SearchSession
    from searchos.harness.telemetry.conversation_context import conversation_turns
    from searchos.skills.catalog.registry import SkillRegistry

    for name in ("enable_skills", "enable_failure_memory", "enable_writer_agent",
                 "enable_access_skill_generation"):
        monkeypatch.setattr(settings, name, False)
    monkeypatch.setattr(settings, "middleware_pipelines", {})
    service = LocalLibraryService(tmp_path / "library")
    library = service.create_library("Deployment rules")
    incoming = tmp_path / "incoming.md"
    incoming.write_text("# Deployment rules\n\n" + FACT)
    document = await service.index_uploaded_file(library.library_id, incoming, "rules.md")
    record, block = service._verified_blocks(library.library_id, [document["document_id"]])[0]
    ref = build_ref_id(library_id=library.library_id, document_id=record.document_id,
                       source_revision=record.source_revision, locators=list(block.source_locators))
    scope = {"mode": "local", "library_id": library.library_id,
             "index_root": library.index_root, "selection": "documents",
             "documents": [record.model_dump(mode="json")]}
    root = tmp_path / "runs"
    workspace = WorkspaceManager(root, "local-session")

    class Extraction:
        async def ainvoke(self, prompt):
            rows = ([{"id": "0", "supported": True}]
                    if "Verify whether each fact" in prompt else
                    [{"finding": FACT, "source_excerpt": FACT,
                      "relation": "supports", "source_urls": [ref]}])
            return SimpleNamespace(content=json.dumps(rows))

    async def plan_handler(count, messages):
        if count == 1:
            return AIMessage(content=SearchRoute(
                path=path, reason="Read authorized rules",
                evidence_obligations=["Read the concurrency limit"],
                strategy=["simple" if path == "simple" else "deep"],
            ).model_dump_json())
        if count == 2:
            # The local scope also determines the omitted role's default.
            return call("enqueue_tasks", {"items_json": json.dumps([{
                "id": "read-rules", "task": "Read the concurrency limit", "kind": "search",
                "result_mode": "findings",
            }])})
        if count == 3:
            return call("check_agents", number=2)
        state = workspace.load_state()
        node = next(node for node in state.evidence_graph.nodes if node.source == ref)
        return AIMessage(content=f"Two jobs. [Rules](evidence:{node.id})")

    async def worker_handler(count, messages):
        if count == 1:
            return call("local_open", {"ref_id": ref})
        return AIMessage(content=f"Two jobs. [Rules]({ref})")

    planner, worker = OfflineModel(handler=plan_handler), OfflineModel(handler=worker_handler)
    extraction = Extraction()
    monkeypatch.setattr(models, "get_model_for", lambda role: (
        extraction if role == "extraction" else worker if role == "sub_agent" else planner))
    harness = SearchSession(workspace_root=str(root), max_time_s=20,
                            skill_registry=SkillRegistry(), skip_synthesis=False)
    result = await harness.run(
        "How many jobs?", session_id="local-session",
        initial_state=SearchState(intent="How many jobs?", source_scope=scope),
    )
    assert not result.execution_error
    answer = (workspace.path / "output/report.md").read_text()
    assert "Two jobs" in answer and ref in answer
    routing = json.loads((workspace.path / "output/routing.json").read_text())
    assert routing.get("final_path", routing["path"]) == path
    assert not routing["escalated"]
    state = workspace.load_state()
    assert state.source_scope == scope
    assert all(task.agent_type == "local_search_agent" for task in state.frontier.questions)
    assert not {"search", "open", "find", "exec", "load_skill"} & set(worker.tool_names)
    assert conversation_turns(workspace.path)[-1]["answer"] == answer
