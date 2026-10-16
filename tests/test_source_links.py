"""内部观测、原文链接与最终引用的回归。"""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from searchos.harness.session import _write_findings_answer
from searchos.socm import EvidenceNode, SearchState
from searchos.tools.schema import _assert_cell_value


def test_unsourced_edit_cannot_overwrite():
    state = SearchState()
    state.coverage_map.add_table("methods", ["name", "safe"], primary_key=["name"])
    state.coverage_map.add_entity("POST", table_id="methods")
    assert not _assert_cell_value(
        state,
        table_id="methods",
        entity="POST",
        attribute="safe",
        value="yes",
        source="agent://orchestrator/edit",
        evidence_prefix="edit",
        alignment_note="format",
        overwrite=True,
    )
    assert not state.evidence_graph.nodes


@pytest.mark.parametrize("source", ["skill://lookup/run/result", "agent://worker/final_summary"])
def test_final_citation_resolves_original_sources(source):
    state = SearchState()
    state.evidence_graph.add_node(
        EvidenceNode(
            id="fact",
            finding="A conclusion",
            source=source,
            source_urls=["https://example.org/original", "https://example.org/second"],
        )
    )
    outputs = {}
    answer = _write_findings_answer(
        SimpleNamespace(write_output=lambda name, value: outputs.update({name: value})),
        state,
        "question",
        {"messages": [AIMessage(content="Claim [source](evidence:fact)")]},
    )
    assert "https://example.org/original" in answer
    assert "https://example.org/second" in answer
    assert "skill://" not in answer and "agent://" not in answer
    assert not json.loads(outputs["result.json"])["citation_issues"]


def test_ambiguous_or_missing_sources_are_not_guessed():
    from searchos.socm.provenance import resolve_answer_citations, select_source_urls

    text = "A from https://example.org/a and B from https://example.org/b"
    assert select_source_urls("skill://lookup/run", text, "B", ["https://example.org/b"]) == [
        "https://example.org/b"
    ]
    assert select_source_urls("skill://lookup/run", text, "B", ["https://invented.org"]) == []
    assert select_source_urls("skill://lookup/run", text, "B") == []
    assert select_source_urls("skill://lookup/run", "https://example.org/a", "A", []) == []
    nodes = [
        EvidenceNode(id="a", source="agent://x/summary", source_urls=["https://example.org/a"]),
        EvidenceNode(id="b", source="agent://x/summary", source_urls=["https://example.org/b"]),
    ]
    answer, issues = resolve_answer_citations("[report](agent://x/summary)", nodes)
    assert answer == "report（原始来源未提供）" and issues
    assert "https://" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["legacy", "portable"])
@pytest.mark.parametrize("table", [False, True])
async def test_skill_page_to_extraction_to_answer(tmp_path, kind, table):
    from searchos.harness.middleware.extraction import (
        ExtractionConfig,
        ExtractionCoordinator,
        InMemoryEvidenceStore,
        WebEvidenceMiddleware,
    )
    from searchos.harness.middleware.extraction.core.commit import ingest_facts
    from searchos.harness.middleware.extraction.core.preparation import OriginalWindowPreparer
    from searchos.harness.middleware.extraction.core.routing import SchemaRouting
    from searchos.socm.workspace import WorkspaceManager
    from searchos.tools import search_state
    from searchos.tools.simple_browser import state as browser_state
    from searchos.tools.simple_browser import tools as browser_tools
    from searchos.tools.simple_browser.execution_pages import register_execution_pages
    from searchos.tools.simple_browser.skill_pages import show_skill_result

    workspace = WorkspaceManager(tmp_path, "origin")
    workspace.create()
    wt = search_state._workspace_var.set(workspace)
    bt = browser_state._browser_var.set(browser_state.BrowserState())
    data = {
        "records": [
            {"name": "Alpha", "value": "42", "source_url": "https://example.org/v1/alpha"},
            {"name": "Beta", "value": "84", "source_url": "https://example.org/v1/beta"},
        ]
    }
    state = SearchState(research_mode="findings")
    if table:
        state.coverage_map.add_table("items", ["name", "value"], primary_key=["name"])
    store = InMemoryEvidenceStore(state)

    class Judge:
        async def ainvoke(self, prompt):
            if "核验每项事实" in prompt:
                rows = [{"id": "0", "supported": True}, {"id": "1", "supported": True}]
            else:
                rows = []
                for row in data["records"]:
                    quote = '"name": "' + row["name"] + '", "value": "' + row["value"] + '"'
                    if table:
                        rows.append(
                            {
                                **row,
                                "_source_excerpt": quote,
                                "_alignment": "full",
                                "_source_urls": {"value": [row["source_url"]]},
                            }
                        )
                    else:
                        rows.append(
                            {
                                "finding": row["name"] + " value " + row["value"],
                                "source_excerpt": quote,
                                "source_urls": [row["source_url"]],
                            }
                        )
            return SimpleNamespace(content=json.dumps(rows))

    config = ExtractionConfig(dual_mode=False, cross_table_backfill=False)
    coordinator = ExtractionCoordinator(
        Judge(),
        store,
        preparer=OriginalWindowPreparer(config),
        routing=SchemaRouting(),
        commit_rows=ingest_facts,
        config=config,
    )
    middleware = WebEvidenceMiddleware(coordinator)
    try:
        if kind == "legacy":
            artifact = {}
            show_skill_result(
                "lookup", {"url": "https://query-not-source.org"}, data, artifact=artifact
            )
            url = artifact["page_source"]["source_url"]
        else:
            saved = tmp_path / "saved"
            saved.mkdir()
            result = register_execution_pages(
                {"execution_id": "run", "status": "completed", "stdout": json.dumps(data)},
                {"name": "lookup", "package_hash": "hash"},
                saved,
                "worker",
            )
            url = result["page_url"]
        # 新 Agent 从持久化页面读取，元数据须跨浏览器和翻页保留。
        browser_state._browser_var.set(browser_state.BrowserState())
        result = await browser_tools.open.ainvoke(
            {"type": "tool_call", "id": "open1", "name": "open", "args": {"id_or_url": url}}
        )
        assert result.artifact["page_source"]["source_urls"] == [
            r["source_url"] for r in data["records"]
        ]

        async def handler(request):
            return result

        await middleware.awrap_tool_call(SimpleNamespace(tool_call={"name": "open"}), handler)
        await coordinator.finalize()
        nodes = store.state.evidence_graph.nodes
        assert len(nodes) == 2
        for node in nodes:
            expected = "alpha" if "Alpha" in node.finding else "beta"
            assert node.source == url
            assert node.source_urls == ["https://example.org/v1/" + expected]
        assert all(o.source_urls for o in store.state.evidence_graph.observations)
        outputs = {}
        answer = _write_findings_answer(
            SimpleNamespace(write_output=lambda name, text: outputs.update({name: text})),
            store.state,
            "query",
            {
                "messages": [
                    AIMessage(
                        content=" ".join(f"{n.finding} [source](evidence:{n.id})" for n in nodes)
                    )
                ]
            },
        )
        assert "skill://" not in answer
        assert all(r["source_url"] in answer for r in data["records"])
    finally:
        browser_state._browser_var.reset(bt)
        search_state._workspace_var.reset(wt)


@pytest.mark.asyncio
async def test_agent_summary_keeps_each_claims_original_link():
    from searchos.harness.middleware.extraction import ExtractionCoordinator, InMemoryEvidenceStore
    from searchos.harness.middleware.extraction.summary_middleware import (
        FinalSummaryEvidenceMiddleware,
    )
    from searchos.harness.middleware.models import TaskContext

    original = EvidenceNode(
        id="original", finding="Alpha is 42", source="https://example.org/v1/alpha"
    )
    state = SearchState(research_mode="findings")
    state.evidence_graph.add_node(original)
    store = InMemoryEvidenceStore(state)

    class Judge:
        async def ainvoke(self, prompt):
            rows = (
                [{"id": "0", "supported": True}, {"id": "1", "supported": True}]
                if "核验每项事实" in prompt
                else [
                    {
                        "finding": "Alpha is 42",
                        "source_excerpt": "Alpha is 42",
                        "source_urls": ["evidence:original"],
                    },
                    {
                        "finding": "Beta is 84",
                        "source_excerpt": "Beta is 84",
                        "source_urls": ["https://example.org/v1/beta"],
                    },
                ]
            )
            return SimpleNamespace(content=json.dumps(rows))

    coordinator = ExtractionCoordinator(Judge(), store)
    middleware = FinalSummaryEvidenceMiddleware(coordinator, context=TaskContext(agent_id="worker"))
    await middleware.aafter_agent(
        {
            "messages": [
                AIMessage(
                    content=(
                        "Alpha is 42 [source](evidence:original). Beta is 84 [source](https://example.org/v1/beta)."
                    )
                )
            ]
        },
        None,
    )
    await coordinator.finalize()
    summaries = [n for n in store.state.evidence_graph.nodes if n.source.startswith("agent://")]
    assert [n.source_urls for n in summaries] == [
        [original.source],
        ["https://example.org/v1/beta"],
    ]


def test_numbered_table_citations_use_original_links():
    from searchos.harness.report.synthesis import (
        _render_scalar_cell,
        build_sources_list,
        build_url_citation_map,
    )

    node = EvidenceNode(
        id="s",
        value="42",
        alignment="full",
        source="skill://lookup/run",
        source_urls=["https://example.org/a", "https://example.org/b"],
    )
    mapping = build_url_citation_map([node])
    assert _render_scalar_cell([node], mapping).endswith("[1] [2]")
    assert "skill://" not in build_sources_list(mapping)
    assert len(mapping) == 2


def test_web_reports_expose_original_urls_and_fact_citations():
    from searchos.tools.tasks import _ground_hybrid_report

    state = SearchState(source_scope={"mode": "web"})
    state.evidence_graph.add_node(
        EvidenceNode(
            id="fact",
            finding="Alpha is 42",
            source="skill://lookup/run",
            source_urls=["https://example.org/v1/alpha"],
        )
    )
    report = {"last_message": "a summary", "evidence_bindings": [{"evidence_id": "fact"}]}
    _ground_hybrid_report(report, state)
    assert report["grounded_findings"][0]["source_urls"] == ["https://example.org/v1/alpha"]
    assert report["grounded_findings"][0]["citation"] == "evidence:fact"
    assert report["agent_report"]["verified"] is False
