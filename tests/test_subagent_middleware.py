"""调度入口完整替换默认 middleware 组合。"""

from types import SimpleNamespace

import pytest

from searchos.agents import runtime
from searchos.agents.orchestrator import lifecycle
from searchos.harness.middleware.context.tool_history_middleware import ToolHistoryMiddleware
from searchos.socm import SearchState


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["search_agent", "explore_agent"])
@pytest.mark.parametrize("enabled", [False, True])
async def test_spawn_uses_exact_custom_middleware(monkeypatch, tmp_path, role, enabled):
    state = SearchState()
    workspace = SimpleNamespace(path=tmp_path, load_state=lambda: state)
    selected = [ToolHistoryMiddleware()] if enabled else []
    captured = {}

    class GraphCaptured(Exception):
        pass

    def graph(**kwargs):
        captured.update(kwargs)
        raise GraphCaptured

    monkeypatch.setattr(runtime, "create_search_agent_graph", graph)
    runtime.set_orchestrator_context(workspace=workspace, model=object())
    with pytest.raises(GraphCaptured):
        await lifecycle._spawn_sub_agent(role, "Read sources", [], middleware=selected)
    assert captured["middleware"] is selected
    assert "# Runtime coverage contract" not in captured["system_prompt"]
    assert "# Legacy budget discipline" not in captured["system_prompt"]


@pytest.mark.asyncio
async def test_candidate_guidance_enters_retrieval_prompt_without_changing_subtask(monkeypatch,tmp_path):
    state=SearchState()
    workspace=SimpleNamespace(path=tmp_path,load_state=lambda:state)
    captured={}
    class GraphCaptured(Exception):pass
    def graph(**kwargs):
        captured.update(kwargs)
        raise GraphCaptured
    monkeypatch.setattr(runtime,'create_search_agent_graph',graph)
    runtime.set_orchestrator_context(workspace=workspace,model=object())
    with pytest.raises(GraphCaptured):
        await lifecycle._spawn_sub_agent('search_agent','查明收入',[],middleware=[],strategy_guidance='检查官方年度报告')
    assert '检查官方年度报告' in captured['system_prompt']
    assert '权限、来源范围和预算仍遵守已有规则' in captured['system_prompt']
