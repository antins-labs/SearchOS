"""写作模型配置必须控制 writer 图，且不影响搜索 Agent。"""

import asyncio
from types import SimpleNamespace

import pytest

from searchos.agents import runtime
from searchos.agents.orchestrator import lifecycle
from searchos.socm import SearchState


@pytest.mark.parametrize(
    ("agent_type", "bind_synthesis", "expected_role"),
    [
        ("writer_agent", True, "synthesis"),
        ("search_agent", True, "sub_agent"),
        ("local_search_agent", True, "sub_agent"),
        ("writer_agent", False, "sub_agent"),
    ],
)
def test_spawn_uses_role_model(monkeypatch, tmp_path, agent_type, bind_synthesis, expected_role):
    models = {role: object() for role in ("main", "sub_agent", "synthesis")}
    state = SearchState(intent="Compare companies")
    workspace = SimpleNamespace(path=tmp_path, load_state=lambda: state)
    captured = {}

    class GraphCaptured(Exception):
        pass

    def capture_graph(**kwargs):
        captured.update(kwargs)
        raise GraphCaptured

    from searchos.config.settings import settings

    monkeypatch.setattr(settings, "enable_writer_agent", True)
    monkeypatch.setattr(runtime, "create_search_agent_graph", capture_graph)

    async def run():
        from searchos.tools.search_state import _source_scope_var

        scope = None
        if agent_type == "local_search_agent":
            from searchos.local.library import LocalLibraryService

            service = LocalLibraryService(tmp_path / "library")
            library = service.create_library("Model selection fixture")
            incoming = tmp_path / "companies.txt"
            incoming.write_text("Acme and Beta are sample companies.")
            document = await service.index_uploaded_file(
                library.library_id,
                incoming,
                "companies.txt",
            )
            record, _ = service._verified_blocks(
                library.library_id,
                [document["document_id"]],
            )[0]
            scope = {
                "mode": "hybrid",
                "index_root": library.index_root,
                "documents": [record.model_dump(mode="json")],
            }
        _source_scope_var.set(scope)
        runtime.set_orchestrator_context(
            workspace=workspace,
            model=models["main"],
            sub_agent_model=models["sub_agent"],
            synthesis_model=models["synthesis"] if bind_synthesis else None,
        )
        with pytest.raises(GraphCaptured):
            await lifecycle._spawn_sub_agent(agent_type, "Compare companies", [])

    asyncio.run(run())
    assert captured["model"] is models[expected_role]


def test_passive_writer_waits_for_capacity_without_losing_trigger(monkeypatch, tmp_path):
    from searchos.agents.orchestrator.scheduler import Scheduler
    from searchos.config.settings import settings

    state = SimpleNamespace(
        intent="Compare companies",
        coverage_map=SimpleNamespace(
            coverage_score=0.5,
            filled_cells=1,
            total_cells=2,
            table_schema=None,
        ),
        evidence_graph=SimpleNamespace(node_count=3),
        frontier=SearchState().frontier,
    )
    workspace = SimpleNamespace(
        path=tmp_path,
        load_state=lambda: state,
        atomic_update_state=lambda update: update(state),
    )
    captured = []

    async def spawn(agent_type, task, skills):
        captured.append((agent_type, task))
        return "writer-1"

    monkeypatch.setattr(settings, "enable_writer_agent", True)
    monkeypatch.setattr(settings, "max_parallel_agents", 1)
    monkeypatch.setattr(lifecycle, "_find_writer_id", lambda: None)
    monkeypatch.setattr(lifecycle, "_spawn_sub_agent", spawn)
    monkeypatch.setattr(lifecycle, "_set_writer_last_evidence_count", lambda *_: None)

    async def run():
        runtime.set_orchestrator_context(workspace=workspace, model=object())
        scheduler = Scheduler()
        lifecycle._ctx.task_pool["busy"] = SimpleNamespace(done=lambda: False)
        assert (await scheduler.maybe_spawn_writer())["action"] == "deferred_pool_full"
        lifecycle._ctx.task_pool.clear()
        result = await scheduler.maybe_spawn_writer()
        assert result["action"] == "spawned"
        assert result["trigger"] == "coverage_stage_50"
        assert state.frontier.questions[0].id == result["write_task_id"]
        assert (await scheduler.maybe_spawn_writer())["action"] == "too_early"

    asyncio.run(run())
    assert len(captured) == 1
    assert captured[0][0] == "writer_agent"
    assert "Coverage crossed 50% (1/2 cells)" in captured[0][1]
