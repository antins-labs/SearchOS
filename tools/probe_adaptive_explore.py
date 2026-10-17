"""用真实模型验证探索路由；检索回报使用明确的固定夹具，不衡量联网答案质量。

运行：python -m tools.probe_adaptive_explore --output tmp/adaptive-explore/probe.json
加 --baseline-ref HEAD 可对比旧版 Web 提示词的初始路由。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from searchos.agents.orchestrator import get_orchestrator_tools
from searchos.agents.orchestrator.catalog import generate_agent_catalog_text
from searchos.agents.orchestrator.prompt import build_orchestrator_prompt
from searchos.agents.runtime import _ctx, set_orchestrator_context
from searchos.agents.toolset_render import render_toolset
from searchos.config.models import get_model_for, resolve_profile
from searchos.config.run_config import EffectiveRunConfig, activate_run_config
from searchos.harness.middleware.context.socm_middleware import SOCMContextMiddleware
from searchos.harness.middleware.models import TaskContext
from searchos.socm import FrontierTask, FrontierTaskStatus, SearchReport, SearchState
from searchos.socm.storage.workspace import WorkspaceManager
from searchos.tools.search_state import _source_scope_var

CASES = [
    (
        "named_attributes",
        "查询阿波罗11号的发射日期、指令长和登月舱名称，提供来源。",
        "search_agent",
    ),
    (
        "bounded_comparison",
        "比较阿波罗11号、12号、14号的发射日期、指令长和登月舱名称，提供来源。",
        "search_agent",
    ),
    (
        "known_roster",
        "按NASA官方阿波罗任务目录，列出阿波罗11号到17号各任务的发射日期。",
        "search_agent",
    ),
    (
        "uncertain_scope",
        "整理所有符合城市级低碳示范区标准的海外项目。各国称呼和认证口径不同，我没有确定候选范围和可比的纳入标准，请先查清这些问题，再汇总项目。",
        "explore_agent",
    ),
]


def baseline_builder(ref):
    source = subprocess.check_output(
        [
            "git",
            "show",
            f"{ref}:searchos/agents/orchestrator/prompt.py",
        ],
        text=True,
    )
    namespace = {"__name__": "adaptive_explore_baseline"}
    exec(compile(source, f"{ref}:prompt.py", "exec"), namespace)
    return namespace["build_orchestrator_prompt"]


@dataclass
class ProbeRequest:
    messages: list


async def mid_search_fixture(workspace, check_agents):
    """构造虚构执行状态，由真实 check_agents 序列化回报与后续提示。"""
    state = workspace.load_state()
    state.frontier.add(
        FrontierTask(
            id="initial_explore",
            question="Identify candidate projects",
            kind="explore",
            agent_type="explore_agent",
            status=FrontierTaskStatus.COMPLETED,
        )
    )
    state.frontier.add(
        FrontierTask(
            id="atlas",
            question="Verify Atlas identity and certification",
            table_id="projects",
            agent_type="search_agent",
            status=FrontierTaskStatus.COMPLETED,
            assigned_agent_id="atlas_search",
        )
    )
    state.frontier.add(
        FrontierTask(
            id="beta",
            question="Verify Beta project's country and certification date only",
            table_id="projects",
            agent_type="search_agent",
            status=FrontierTaskStatus.RUNNING,
            assigned_agent_id="beta_search",
            target_cells=["Beta.Country", "Beta.Status"],
        )
    )
    workspace.save_state(state)
    report = SearchReport(
        agent_id="atlas_search",
        task_ids=["atlas"],
        status="completed",
        result="Atlas identity and certification definitions remain unresolved.",
        last_message=(
            "Fixture: Earlier exploration identified Atlas. Search found three unrelated "
            "initiatives and conflicting certification definitions. Their identities and "
            "eligibility remain uncertain. Sources: https://example.org/atlas-a and "
            "https://example.org/atlas-b. Beta's independent country/date lookup cannot "
            "resolve Atlas identity or these certification definitions."
        ),
    )
    loop = asyncio.get_running_loop()
    finished = loop.create_future()
    finished.set_result(None)
    _ctx.task_pool.update({"atlas_search": finished, "beta_search": loop.create_future()})
    _ctx.completed["atlas_search"] = report
    return await check_agents.ainvoke({"timeout": 0.01})


async def routing_case(case, builder, variant, output_dir, *, for_eval=False):
    case_id, query, expected = case
    started = time.monotonic()
    tools = get_orchestrator_tools(source_mode="web")
    tool_map = {tool.name: tool for tool in tools}
    model = get_model_for("orchestrator").bind_tools(tools)
    scope = {"mode": "web", "documents": []}
    token = _source_scope_var.set(scope)
    trace, agents, recreated, waited = [], [], False, False
    with TemporaryDirectory(prefix="planning-", dir=output_dir) as root:
        workspace = WorkspaceManager(root, case_id)
        workspace.create()
        state = SearchState(intent=query, source_scope=scope)
        mid_search = case_id == "mid_search_uncertainty"
        initial_explore = (
            variant == "current" and EffectiveRunConfig.from_settings(for_eval=for_eval).explore_on_start
        )
        if initial_explore and not mid_search:
            expected = "explore_agent"
        if mid_search:
            state.coverage_map.add_table(
                "projects",
                ["Name", "Country", "Status"],
                primary_key=["Name"],
                entities=["Atlas", "Beta"],
            )
        workspace.save_state(state)
        set_orchestrator_context(workspace=workspace, model=model)
        prompt = builder(
            agent_catalog=generate_agent_catalog_text(),
            skill_catalog="",
            source_mode="web",
            current_time=datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d"),
            orch_toolset=render_toolset(tools),
            max_search_agents_per_session=12,
            **({"explore_on_start": initial_explore} if variant == "current" else {}),
        )
        messages = [SystemMessage(content=prompt), HumanMessage(content=query)]
        if mid_search:
            fixture = await mid_search_fixture(workspace, tool_map["check_agents"])
            messages.extend(
                [
                    AIMessage(
                        content="已有 projects 表。核实 Atlas，同时独立检索 Beta。",
                        tool_calls=[{"name": "check_agents", "args": {}, "id": "collect"}],
                    ),
                    ToolMessage(tool_call_id="collect", name="check_agents", content=fixture),
                ]
            )
        socm = SOCMContextMiddleware(
            workspace,
            task=TaskContext(agent_id="orchestrator"),
            view="overview",
        )

        async def invoke(request):
            return await model.ainvoke(request.messages)

        try:
            for _ in range(4):
                reply = await asyncio.wait_for(
                    socm.awrap_model_call(ProbeRequest(messages), invoke),
                    90,
                )
                messages.append(reply)
                trace.append(
                    {
                        "content": reply.content,
                        "calls": reply.tool_calls,
                        "usage": reply.usage_metadata,
                        "state_snapshot": socm._last_text,
                    }
                )
                for call in reply.tool_calls:
                    if mid_search and call["name"] == "create_schema":
                        recreated = True
                    if mid_search and call["name"] == "check_agents":
                        waited = True
                    if call["name"] == "enqueue_tasks":
                        items = json.loads(call["args"]["items_json"])
                        agents.extend(item.get("agent_type", "search_agent") for item in items)
                if agents or not reply.tool_calls:
                    break
                for call in reply.tool_calls:
                    if call["name"] in {
                        "create_schema",
                        "add_entities",
                        "add_columns",
                        "edit_entities",
                        "inspect_table",
                        "read_evidence",
                        "list_frontier",
                    }:
                        result = await tool_map[call["name"]].ainvoke(call["args"])
                    elif mid_search and call["name"] == "check_agents":
                        result = await tool_map["check_agents"].ainvoke({"timeout": 0.01})
                    else:
                        result = json.dumps(
                            {"error": "Inspect the supplied state; this probe stops at dispatch."}
                        )
                    messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
                    trace[-1].setdefault("tool_results", []).append(
                        {
                            "name": call["name"],
                            "result": str(result),
                        }
                    )
            passed = expected in agents and not recreated and not waited
            if expected == "search_agent":
                passed = passed and "explore_agent" not in agents
            if initial_explore and not mid_search:
                passed = passed and (
                    trace[0]["calls"][0]["name"] == "enqueue_tasks"
                    and all(agent == "explore_agent" for agent in agents)
                    and all(call["name"] == "enqueue_tasks" for call in trace[0]["calls"])
                )
            row = {
                "case": case_id,
                "variant": variant,
                "expected": expected,
                "passed": passed,
                "agents": agents,
                "trace": trace,
            }
        except Exception as error:
            row = {
                "case": case_id,
                "variant": variant,
                "passed": False,
                "error": type(error).__name__,
                "trace": trace,
            }
        finally:
            for future in _ctx.task_pool.values():
                if not future.done():
                    future.cancel()
            _source_scope_var.reset(token)
    row["duration_s"] = round(time.monotonic() - started, 2)
    print(f"{variant}/{case_id}: passed={row['passed']} agents={row.get('agents', [])}", flush=True)
    return row


async def early_brief_case():
    from langchain_core.tools import tool

    from searchos.agents.explore import get_tools
    from searchos.harness.middleware.extraction import TaskContext
    from searchos.harness.middleware.pipelines import explore_pipeline

    calls = []

    @tool
    def explore_web(queries: list[str], open_top_k: int = 1, max_results_per_query: int = 5) -> str:
        """检索并阅读来源；本验证返回固定来源夹具。"""
        calls.append(queries)
        return (
            "Fixture opened source: https://example.org/registry\n"
            "Official registry, 2026. The requested scope consists of exactly two certified "
            "programmes: Alpha and Beta. This registry is the complete authoritative list "
            "for the specified certification and year. Detail pages: "
            "https://example.org/alpha and https://example.org/beta."
        )

    prompt = (
        Path("searchos/agents/explore/agent.md")
        .read_text()
        .replace(
            "{toolset}",
            render_toolset(get_tools()),
        )
    )
    graph = explore_pipeline(
        model=get_model_for("sub_agent"),
        tools=[explore_web],
        workspace=None,
        task=TaskContext(agent_id="explore_probe"),
        system_prompt=prompt,
    )
    result = await asyncio.wait_for(
        graph.ainvoke(
            {
                "messages": [
                    (
                        "user",
                        "Locate the complete official registry for 2026 certified programmes "
                        "and return the next retrieval routes. No attribute extraction is needed.",
                    )
                ]
            },
            {"configurable": {"thread_id": "early-brief"}},
        ),
        120,
    )
    final = result["messages"][-1]
    return {
        "case": "early_brief",
        "variant": "current",
        "passed": len(calls) == 1 and not final.tool_calls,
        "waves": len(calls),
        "queries": calls,
        "brief": final.content,
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-ref")
    parser.add_argument("--for-eval", action="store_true", help="使用评测默认的启动 Explore 策略。")
    parser.add_argument(
        "--case",
        action="append",
        choices=[case[0] for case in CASES] + ["mid_search_uncertainty", "early_brief"],
        help="只运行指定场景，可重复传入。默认运行全部场景。",
    )
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(Path(".env"), override=False)
    from searchos.config.web_overlay import apply_to_runtime, load_overlay_file

    load_overlay_file()
    apply_to_runtime()
    from searchos.config.settings import settings

    # 本脚本只验证派发决策，使用内存 Future 表示在途工作，不启动真实检索。
    settings.enable_scheduler = False
    settings.enable_writer_agent = False
    run_config = EffectiveRunConfig.from_settings(for_eval=args.for_eval)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    report = {
        "model": resolve_profile("orchestrator").model,
        "temperature": resolve_profile("orchestrator").temperature,
        "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "run_config": run_config.snapshot(),
        "baseline_commit": subprocess.check_output(
            ["git", "rev-parse", args.baseline_ref],
            text=True,
        ).strip()
        if args.baseline_ref
        else None,
        "scope": "真实模型路由与固定来源夹具；不执行联网检索，不测量答案质量。",
        "results": rows,
    }
    variants = [("current", build_orchestrator_prompt)]
    if args.baseline_ref:
        variants.insert(0, ("baseline", baseline_builder(args.baseline_ref)))
    for variant, builder in variants:
        for case in CASES:
            if args.case and case[0] not in args.case:
                continue
            rows.append(await routing_case(
                case, builder, variant, args.output.parent, for_eval=args.for_eval,
            ))
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            if "error" in rows[-1]:
                raise SystemExit("模型调用失败；已保存结果，停止后续调用。")
    if not args.case or "mid_search_uncertainty" in args.case:
        rows.append(
            await routing_case(
                (
                    "mid_search_uncertainty",
                    "汇总符合城市级低碳示范区标准的海外项目，核实各项目的身份和认证状态。",
                    "explore_agent",
                ),
                build_orchestrator_prompt,
                "current",
                args.output.parent,
                for_eval=args.for_eval,
            )
        )
    if not args.case or "early_brief" in args.case:
        try:
            with activate_run_config(run_config):
                rows.append(await early_brief_case())
        except Exception as error:
            rows.append(
                {
                    "case": "early_brief",
                    "variant": "current",
                    "passed": False,
                    "error": type(error).__name__,
                }
            )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if not all(row["passed"] for row in rows if row["variant"] == "current"):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
