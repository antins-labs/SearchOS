from searchos.harness.middleware.sensor.core.models import ControlState

"""Web 与本地检索 Agent 必须保持工具和路由隔离。"""

import asyncio
from types import SimpleNamespace

import pytest

from searchos.agents import local_search, runtime, search
from searchos.agents.orchestrator import catalog, lifecycle
from searchos.agents.orchestrator.prompt import build_orchestrator_prompt
from searchos.config.settings import settings
from searchos.socm import SearchState
from searchos.tools.search_state import _source_scope_var


def _tool_names(tools: list) -> set[str]:
    return {str(getattr(tool, "name", "")) for tool in tools}


def test_web_and_local_agent_toolsets_are_isolated(monkeypatch):
    monkeypatch.setattr(settings, "enable_skills", False)
    monkeypatch.setattr(settings, "enable_local_tools", True)
    monkeypatch.setattr(settings, "local_allow_model_access", True)

    web_names = _tool_names(search.get_tools())
    local_names = _tool_names(local_search.get_tools())

    assert not {"local_catalog", "local_open", "local_find"} & web_names
    assert local_names == {"local_catalog", "local_open", "local_find"}
    assert not {"search", "open", "find"} & local_names
    assert not any(name.startswith("skill_") for name in local_names)


def test_local_agent_catalog_requires_explicit_run_scope(monkeypatch):
    monkeypatch.setattr(settings, "enable_local_tools", True)
    monkeypatch.setattr(settings, "local_allow_model_access", False)
    assert "local_search_agent" not in catalog.generate_agent_catalog_text()

    monkeypatch.setattr(settings, "local_allow_model_access", True)
    assert "local_search_agent" not in catalog.generate_agent_catalog_text()
    token = _source_scope_var.set({"mode": "hybrid", "documents": [{"document_id": "selected"}]})
    try:
        rendered = catalog.generate_agent_catalog_text()
        assert "local_search_agent" in rendered
        assert "local_catalog, local_open, local_find" in rendered
    finally:
        _source_scope_var.reset(token)


def test_search_kind_still_defaults_to_web_agent():
    assert lifecycle._KIND_TO_AGENT_BY_KIND["search"] == "search_agent"
    assert lifecycle._KIND_FROM_AGENT["local_search_agent"] == "search"
    assert lifecycle._ROLE_REGISTRY["local_search_agent"] is local_search


def test_orchestrator_defaults_to_web_and_hybrid_must_be_explicit():
    prompt = build_orchestrator_prompt(
        agent_catalog="agents",
        skill_catalog="skills",
        current_time="2026-09-10",
    )
    assert "Use `search_agent` for web evidence" in prompt
    assert "local_search_agent" not in prompt
    assert "hybrid" not in prompt.lower()
    hybrid = build_orchestrator_prompt("agents", "skills", source_mode="hybrid")
    assert "Source mode:" not in hybrid
    assert "hybrid" not in hybrid.lower()
    assert 'result_mode="findings"' in hybrid
    with pytest.raises(ValueError, match="direct Local Search Agent"):
        build_orchestrator_prompt("agents", "skills", source_mode="local")


def test_local_spawn_discards_web_access_skills(monkeypatch, tmp_path):
    state = SearchState(intent="Summarize a local paper")
    workspace = SimpleNamespace(path=tmp_path, load_state=lambda: state)
    captured: dict = {}

    class GraphCaptured(Exception):
        pass

    def capture_tools(skill_names=None, **kwargs):
        captured["skill_names"] = skill_names
        return []

    def capture_graph(**kwargs):
        captured["system_prompt"] = kwargs["system_prompt"]
        captured["middleware"] = kwargs["middleware"]
        raise GraphCaptured

    monkeypatch.setattr(local_search, "get_tools", capture_tools)
    monkeypatch.setattr(runtime, "create_search_agent_graph", capture_graph)

    async def run():
        from searchos.local.library import LocalLibraryService

        service = LocalLibraryService(tmp_path / "data")
        library = service.create_library("Selected documents")
        incoming = tmp_path / "incoming.txt"
        incoming.write_text("A local paper about document retrieval.")
        doc = await service.index_uploaded_file(library.library_id, incoming, "paper.txt")
        record, _ = service._verified_blocks(library.library_id, [doc["document_id"]])[0]
        _source_scope_var.set({"mode": "hybrid", "index_root": library.index_root,
                               "documents": [record.model_dump(mode="json")]})
        runtime.set_orchestrator_context(workspace=workspace, model=object())
        with pytest.raises(GraphCaptured):
            await lifecycle._spawn_sub_agent(
                "local_search_agent", "Read the local paper", ["example_web_skill"]
            )

    asyncio.run(run())
    assert captured["skill_names"] == []
    assert "example_web_skill" not in captured["system_prompt"]

    from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
    harness = next(m for m in captured["middleware"] if isinstance(m, BudgetMiddleware))
    assert harness.budget.max_queries == 15
    assert harness.budget.max_opens == 15
    assert harness.budget.max_finds == 15
    assert "# Tool budget" not in captured["system_prompt"]


def test_local_tool_budgets_block_each_dimension_without_logging():
    from searchos.harness.middleware.sensor.budget_middleware import BudgetMiddleware
    from searchos.harness.middleware.sensor.core.models import BudgetState

    budget = BudgetState(max_queries=1, max_opens=1, max_finds=1)
    harness = BudgetMiddleware(budget=budget, control=ControlState())
    executed = []

    async def handler(request):
        executed.append(request.tool_call["name"])
        return "local result"

    async def run():
        for name in ("local_catalog", "local_open", "local_find"):
            for attempt in range(2):
                response = await harness.awrap_tool_call(SimpleNamespace(
                    tool_call={"name": name, "args": {}, "id": f"{name}-{attempt}"},
                ), handler)
                if attempt:
                    assert "blocked" in response.content.lower()
        assert executed == ["local_catalog", "local_open", "local_find"]
        assert budget.consumed_queries == budget.consumed_opens == budget.consumed_finds == 1
        assert budget.fully_exhausted

    asyncio.run(run())
