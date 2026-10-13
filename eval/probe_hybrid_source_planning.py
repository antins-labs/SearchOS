"""使用虚构资料验证真实 Orchestrator 的来源与后续调度决策；不执行检索工具。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from searchos.agents.orchestrator import get_orchestrator_tools
from searchos.agents.orchestrator.catalog import generate_agent_catalog_text
from searchos.agents.orchestrator.prompt import build_orchestrator_prompt
from searchos.agents.toolset_render import render_toolset
from searchos.config.models import get_model_for
from searchos.tools.search_state import _source_scope_var

CASES = [
    {
        "id": "resolve_local_reference",
        "query": "基于 Atlas 方案，找一些采用相似方法的公开项目。",
        "local": True,
        "expected": "local_search_agent",
    },
    {
        "id": "local_comparison",
        "query": "比较库里的两份实施方案，解释它们的关键取舍，不需要外部资料。",
        "local": True,
        "expected": "local_search_agent",
    },
    {
        "id": "unrelated_current_web",
        "query": "查找欧洲航天局今天发布的最新新闻，给出官网链接。",
        "local": True,
        "expected": "web",
    },
    {
        "id": "no_local_scope",
        "query": "查找公开的文件检索系统，解释它们的主要差异。",
        "local": False,
        "expected": "web",
    },
]


async def main():
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    from searchos.config.web_overlay import load_and_apply

    load_and_apply()
    tools = get_orchestrator_tools(source_mode="hybrid")
    model = get_model_for("orchestrator").bind_tools(tools)
    results = []
    for case in CASES:
        token = _source_scope_var.set(
            {"mode": "hybrid", "documents": [{"document_id": "atlas"}] if case["local"] else []}
        )
        try:
            prompt = build_orchestrator_prompt(
                agent_catalog=generate_agent_catalog_text(),
                skill_catalog="",
                source_mode="hybrid",
                current_time="2026-09-14",
                max_search_agents_per_session=12,
                orch_toolset=render_toolset(tools),
                local_sources=(
                    "Current library: Design notes; scope: readable library snapshot.\n"
                    "- Atlas implementation.md\n- Beacon implementation.md"
                )
                if case["local"]
                else "",
            )
            reply = await asyncio.wait_for(
                model.ainvoke([SystemMessage(content=prompt), HumanMessage(content=case["query"])]),
                120,
            )
            calls = reply.tool_calls
            agents = []
            for call in calls:
                if call["name"] == "enqueue_tasks":
                    agents.extend(
                        item.get("agent_type") for item in json.loads(call["args"]["items_json"])
                    )
            ok = (
                case["expected"] in agents
                if case["expected"] != "web"
                else bool(set(agents) & {"search_agent", "explore_agent"})
                and "local_search_agent" not in agents
            )
            results.append(
                {"case": case["id"], "passed": ok, "calls": calls, "content": reply.content}
            )
            if case["id"] == "resolve_local_reference" and ok:
                # 工具回报是虚构夹具；这里验证模型读取回报后的规划，不执行真实检索。
                messages = [
                    SystemMessage(content=prompt),
                    HumanMessage(content=case["query"]),
                    reply,
                ]
                continuation = []
                facts = [
                    {
                        "id": "atlas-method",
                        "finding": (
                            "Atlas is a document-retrieval prototype. It routes a question "
                            "through a "
                            "hierarchy of topic summaries to select documents, then reads bounded "
                            "source windows to verify claims. It targets long technical "
                            "collections "
                            "and trades exhaustive scanning for narrower traversal. It uses "
                            "no vector "
                            "index. The implementation is a prototype without public "
                            "benchmark results."
                        ),
                        "source": "local://synthetic/atlas",
                        "citation": "evidence:atlas-method",
                        "valid": True,
                        "source_excerpt": (
                            "Hierarchical topic routing followed by source verification."
                        ),
                    }
                ]
                queued_ids = []
                for _ in range(8):
                    for call in reply.tool_calls:
                        if call["name"] == "enqueue_tasks":
                            queued_ids = [
                                item.get("id", "atlas")
                                for item in json.loads(call["args"]["items_json"])
                            ]
                            result = {"queued": queued_ids, "pool": {"running": len(queued_ids)}}
                        elif call["name"] == "check_agents":
                            result = {
                                "remaining": 0,
                                "reports": [
                                    {
                                        "task_id": task_id,
                                        "kind": "search",
                                        "status": "completed",
                                        "grounded_findings": facts,
                                        "agent_report": (
                                            "Read the implementation overview "
                                            "and design tradeoffs; "
                                            "source facts committed."
                                        ),
                                    }
                                    for task_id in queued_ids
                                ],
                            }
                        elif call["name"] == "read_evidence":
                            result = {"nodes": facts, "count": len(facts)}
                        elif call["name"] == "create_schema":
                            result = {"status": "created", "tables": []}
                        else:
                            result = {"status": "completed"}
                        messages.append(
                            ToolMessage(content=json.dumps(result), tool_call_id=call["id"])
                        )
                    reply = await asyncio.wait_for(model.ainvoke(messages), 120)
                    messages.append(reply)
                    continuation.extend(reply.tool_calls)
                    web_tasks = [
                        item
                        for call in reply.tool_calls
                        if call["name"] == "enqueue_tasks"
                        for item in json.loads(call["args"]["items_json"])
                        if item.get("agent_type") in {"search_agent", "explore_agent"}
                    ]
                    if web_tasks or not reply.tool_calls:
                        break
                results.append(
                    {
                        "case": "local_findings_to_web",
                        "passed": bool(web_tasks),
                        "calls": continuation,
                    }
                )
            output = Path("/tmp/hybrid-planning-probe.json")
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
            print(f"{case['id']}: {ok}; roles={agents}", flush=True)
        finally:
            _source_scope_var.reset(token)
    if not all(result["passed"] for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
