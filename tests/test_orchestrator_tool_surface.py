"""Hybrid 主 Agent 只承担调度、结构管理和状态读取。"""
from searchos.agents.orchestrator import get_orchestrator_tools
from searchos.agents.orchestrator.prompt import build_orchestrator_prompt
from searchos.agents.toolset_render import render_toolset


def test_hybrid_tool_surface_excludes_manual_evidence_operations():
    tools = get_orchestrator_tools(source_mode="hybrid")
    assert {tool.name for tool in tools} == {
        "create_schema", "add_columns", "add_entities", "remove_entities", "edit_entities", "inspect_table",
        "enqueue_tasks", "stop_task", "check_agents", "read_evidence", "list_frontier", "python",
    }
    prompt = build_orchestrator_prompt("agents", "skills", source_mode="hybrid",
                                       orch_toolset=render_toolset(tools))
    for name in ("bind_evidence", "project_evidence", "extract_observation"):
        assert name not in prompt


def test_orchestrator_excludes_manual_evidence_operations_in_all_modes():
    forbidden = {"bind_evidence", "project_evidence", "extract_observation"}
    for mode in ("", "web", "hybrid"):
        names = {tool.name for tool in get_orchestrator_tools(source_mode=mode)}
        assert names.isdisjoint(forbidden)


def test_rendered_prompts_and_tools_do_not_explain_source_modes():
    import re
    for mode in ("web", "hybrid"):
        tools = get_orchestrator_tools(source_mode=mode)
        prompt = build_orchestrator_prompt("Available agents", "Available skills",
            source_mode=mode, orch_toolset=render_toolset(tools))
        assert not re.search(r"source mode:|web mode|local mode|in hybrid|hybrid mode", prompt, re.I)
