"""验证探索可选、可反复派发，以及运行中的检索和依赖边界。"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from searchos.agents import runtime
from searchos.agents.orchestrator import lifecycle
from searchos.config.settings import settings
from searchos.socm import FrontierTaskStatus, SearchState
from searchos.socm.workspace import WorkspaceManager
from searchos.tools.search_state import _source_scope_var
from searchos.tools.tasks import _agent_creation_limit_for_frontier_kind, enqueue_tasks


@pytest.mark.asyncio
async def test_search_then_repeated_explore_preserves_independent_work_and_dependencies(
    tmp_path,
    monkeypatch,
):
    workspace = WorkspaceManager(tmp_path, "adaptive-explore")
    workspace.create()
    state = SearchState(source_scope={"mode": "web"})
    state.coverage_map.add_table(
        "programmes",
        ["Name", "Credits"],
        primary_key=["Name"],
        entities=["Alpha"],
    )
    workspace.save_state(state)
    runtime.set_orchestrator_context(workspace=workspace, model=object())
    token = _source_scope_var.set(state.source_scope)
    monkeypatch.setattr(settings, "max_parallel_agents", 2)
    monkeypatch.setattr(settings, "enable_explore", True)
    monkeypatch.setattr(settings, "enable_scheduler", True)
    monkeypatch.setattr(settings, "enable_writer_agent", False)
    monkeypatch.setattr(settings, "spawn_stagger_s", 0)
    spawned = []

    async def spawn(agent_type, prompt, skills, *, bind_task_id, **kwargs):
        spawned.append((agent_type, bind_task_id))
        agent_id = f"{agent_type}-{len(spawned)}"
        runtime._ctx.task_pool[agent_id] = asyncio.get_running_loop().create_future()

        def bind(s):
            task = next(q for q in s.frontier.questions if q.id == bind_task_id)
            task.status = FrontierTaskStatus.RUNNING
            task.assigned_agent_id = agent_id
            return s

        workspace.atomic_update_state(bind)
        runtime._ctx.agent_graphs[agent_id] = {
            "agent_type": agent_type,
            "assigned_task_id": bind_task_id,
        }
        return agent_id

    monkeypatch.setattr(lifecycle, "_spawn_sub_agent", spawn)

    async def enqueue(role, task, **extra):
        result = json.loads(
            await enqueue_tasks.ainvoke(
                {
                    "items_json": json.dumps(
                        [
                            {"agent_type": role, "task": task, **extra},
                        ]
                    )
                }
            )
        )
        assert not result["errors"] and not result["rejected"]
        return result["queued"][0]

    try:
        # 先派发 Search，不依赖任何 Explore。
        search_id = await enqueue("search_agent", "Verify Alpha credits", target_table="programmes")
        assert spawned == [("search_agent", search_id)]
        search_future = next(iter(runtime._ctx.task_pool.values()))

        # 超过过去最大档位的两次创建限制；完成通过真实报告回收路径更新 Frontier。
        for number in range(3):
            explore_id = await enqueue("explore_agent", f"Resolve new scope uncertainty {number}")
            assert spawned[-1] == ("explore_agent", explore_id)
            explore_agent = next(
                aid
                for aid, info in runtime._ctx.agent_graphs.items()
                if info["assigned_task_id"] == explore_id
            )
            dependent_id = None
            if number == 2:
                dependent_id = await enqueue(
                    "search_agent",
                    "Retrieve newly identified programme duration",
                    blocked_by=[explore_id],
                    target_table="programmes",
                )
                assert not any(tid == dependent_id for _, tid in spawned)
            runtime._ctx.task_pool[explore_agent].set_result(None)
            report = lifecycle._compute_agent_report(
                agent_id=explore_agent,
                thread_id=explore_agent,
                pre_snapshot={},
                started_at=0,
                status="completed",
                result="Resolved scope",
                last_ai_text="Resolved; use Alpha.",
            )
            assert report.kind == "explore" and report.status == "completed"
            if dependent_id:
                await runtime._scheduler().tick()
                assert spawned[-1] == ("search_agent", dependent_id)
            assert not search_future.done()

        after = workspace.load_state()
        assert after.coverage_map == state.coverage_map
        assert after.evidence_graph == state.evidence_graph
    finally:
        for task in runtime._ctx.task_pool.values():
            if not task.done():
                task.cancel()
        _source_scope_var.reset(token)


def test_retired_explore_limit_cannot_restrict_dispatch_or_discard_other_overrides():
    from searchos.config.effort import EFFORT_KEYS, EFFORT_LEVELS
    from searchos.config.web_overlay import WebSettings

    legacy_settings = SimpleNamespace(max_explore_agents_per_session=1)
    assert _agent_creation_limit_for_frontier_kind(legacy_settings, "explore") == 0
    overlay = WebSettings.model_validate(
        {
            "effort": {
                "level": "low",
                "overrides": {
                    "max_explore_agents_per_session": 1,
                    "max_search_agents_per_session": 7,
                },
            }
        }
    )
    assert overlay.effort.overrides == {"max_search_agents_per_session": 7}
    assert "max_explore_agents_per_session" not in EFFORT_KEYS
    assert all("max_explore_agents_per_session" not in knobs for knobs in EFFORT_LEVELS.values())


def test_disabled_explore_is_not_available_to_dispatch(monkeypatch):
    from searchos.agents.orchestrator.catalog import _is_agent_enabled

    monkeypatch.setattr(settings, "enable_explore", False)
    assert not _is_agent_enabled("explore_agent")
