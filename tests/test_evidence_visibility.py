"""证据读取、引用和导出的一致性回归。"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from searchos.harness.answer_stream import AnswerStreamEmitter
from searchos.harness.report.eval_table_export import build_eval_table
from searchos.harness.report.synthesis import (
    build_coverage_table_with_citations,
    build_url_citation_map,
)
from searchos.socm import EvidenceNode, EvidenceStatus, OutlineSection, SearchState
from searchos.tools import socm_read, writer
from searchos.tools.writer import _ensure_ev_ids


def _state():
    state = SearchState()
    state.coverage_map.add_table("t", ["Value"], entities=["A", "B"])
    return state


def _node(node_id, **kwargs):
    fields = dict(
        id=node_id,
        table_id="t",
        entity="A",
        attribute="Value",
        value=node_id,
        source=f"https://example.com/{node_id}",
        alignment="full",
        confidence=0.9,
        source_authority="news",
        span=(0, 3),
    )
    fields.update(kwargs)
    return EvidenceNode(**fields)


def _commit(state, *nodes):
    for node in nodes:
        state.evidence_graph.add_node(node)
    state.coverage_map.fill_from_evidence(list(nodes))


def _report(state):
    nodes = state.evidence_graph.nodes
    return build_coverage_table_with_citations(
        state,
        {n.id: n for n in nodes},
        build_url_citation_map(nodes),
    )


def test_exports_use_the_same_winner_as_coverage():
    state = _state()
    page = _node("page", value="100")
    assertion = _node(
        "f_assert_1",
        value="999",
        source="agent://orchestrator/asserted",
        confidence=0.7,
        source_authority="aggregator",
        span=None,
    )
    _commit(state, page, assertion)
    assert state.coverage_map.cells["t/A.Value"].display_hint == "100"
    for rendered in (_report(state), build_eval_table(state)):
        assert "100" in rendered
        assert "999" not in rendered


@pytest.mark.parametrize("wrong_binding", ["entity", "table", "attribute"])
def test_exports_ignore_historical_wrong_cell_references(wrong_binding):
    state = _state()
    state.coverage_map.add_table("other", ["Value"], entities=["A"])
    fields = {
        "entity": {"entity": "B"},
        "table": {"table_id": "other"},
        "attribute": {"attribute": "Other"},
    }[wrong_binding]
    node = _node("wrong", value="WRONG", **fields)
    state.evidence_graph.add_node(node)
    state.coverage_map.cells["t/A.Value"].supporting_evidence_ids.append(node.id)
    for rendered in (_report(state), build_eval_table(state)):
        assert "WRONG" not in rendered


def _visibility_state():
    state = _state()
    _commit(
        state,
        _node("visible"),
        _node("removed", entity="B"),
        _node("rejected", status=EvidenceStatus.REJECTED),
        _node("superseded", status=EvidenceStatus.SUPERSEDED),
        _node("freeform", entity="", attribute="", table_id=""),
    )
    state.coverage_map.remove_entity("B", table_id="t", reason="outside scope")
    return state


def test_default_read_hides_ineligible_evidence_and_audit_explains_it(monkeypatch):
    state = _visibility_state()
    monkeypatch.setattr(socm_read, "_ws", lambda: SimpleNamespace(load_state=lambda: state))
    normal = json.loads(asyncio.run(socm_read.read_evidence.ainvoke({})))
    assert {n["id"] for n in normal["nodes"]} == {"visible", "freeform"}
    audit = json.loads(asyncio.run(socm_read.read_evidence.ainvoke({"include_inactive": True})))
    rows = {n["id"]: n for n in audit["nodes"]}
    assert set(rows) == {"visible", "freeform", "removed", "rejected", "superseded"}
    assert rows["removed"]["row_status"] == "excluded"
    assert rows["removed"]["table_id"] == "t"
    assert rows["removed"]["exclusion_reason"] == "outside scope"
    assert rows["rejected"]["status"] == "rejected"


def test_read_missing_cell_does_not_fall_back_to_recent_nodes(monkeypatch):
    state = _visibility_state()
    monkeypatch.setattr(socm_read, "_ws", lambda: SimpleNamespace(load_state=lambda: state))
    result = json.loads(asyncio.run(socm_read.read_evidence.ainvoke({"cell": "t/B.Value"})))
    assert result["nodes"] == []


def test_writer_rejects_removed_and_inactive_evidence():
    good, bad = _ensure_ev_ids(
        _visibility_state(),
        ["visible", "freeform", "removed", "rejected", "superseded"],
    )
    assert good == ["visible", "freeform"]
    assert bad == ["removed", "rejected", "superseded"]


def test_writer_cannot_keep_removed_citations_during_edit(monkeypatch):
    state = _visibility_state()
    state.outline.sections.append(
        OutlineSection(
            id="summary",
            content="before",
            cited_evidence_ids=["removed"],
        )
    )
    monkeypatch.setattr(writer, "_require_writer", lambda op: None)
    monkeypatch.setattr(writer, "_ws", lambda: SimpleNamespace(load_state=lambda: state))
    result = json.loads(
        asyncio.run(
            writer.edit_section.ainvoke(
                {
                    "section_id": "summary",
                    "old_string": "before",
                    "new_string": "after",
                }
            )
        )
    )
    assert "ineligible" in result["error"]
    assert state.outline.sections[0].content == "before"


def test_writer_rechecks_eligibility_inside_atomic_commit(monkeypatch):
    state = _state()
    _commit(state, _node("visible"))

    def atomic_update(update):
        state.coverage_map.remove_entity("A", table_id="t", reason="removed concurrently")
        return update(state)

    monkeypatch.setattr(writer, "_require_writer", lambda op: None)
    monkeypatch.setattr(
        writer,
        "_ws",
        lambda: SimpleNamespace(
            load_state=lambda: state,
            atomic_update_state=atomic_update,
        ),
    )
    result = json.loads(
        asyncio.run(
            writer.write_section.ainvoke(
                {
                    "section_id": "summary",
                    "content": "after",
                    "cited_evidence_ids": "visible",
                }
            )
        )
    )
    assert "ineligible" in result["error"]
    assert state.outline.sections == []


def test_citation_map_excludes_inactive_and_internal_sources():
    mapping = build_url_citation_map(
        [
            _node("visible"),
            _node("internal", source="agent://orchestrator/asserted"),
            _node("rejected", status=EvidenceStatus.REJECTED),
        ]
    )
    assert mapping == {"https://example.com/visible": 1}


def test_final_sources_only_include_visible_evidence(monkeypatch):
    from searchos.harness import session

    state = _visibility_state()
    state.outline.sections.extend(
        [
            OutlineSection(id="valid", content="KEEP_THIS_CLAIM", cited_evidence_ids=["visible"]),
            OutlineSection(id="invalid", content="DROP_THIS_CLAIM", cited_evidence_ids=["removed"]),
        ]
    )
    outputs = {}

    async def no_writer(**kwargs):
        return None

    monkeypatch.setattr(session, "_run_writer_finalize", no_writer)
    workspace = SimpleNamespace(session_id="visibility", write_output=outputs.__setitem__)
    asyncio.run(
        session._harness_synthesize(
            workspace=workspace,
            state=state,
            query="test",
        )
    )
    result = json.loads(outputs["result.json"])
    assert set(result["url_citations"]) == {
        "https://example.com/visible",
        "https://example.com/freeform",
    }
    assert "https://example.com/removed" not in outputs["report.md"]
    assert "KEEP_THIS_CLAIM" in outputs["report.md"]
    assert "DROP_THIS_CLAIM" not in outputs["report.md"]
    assert len(state.outline.sections) == 2


@pytest.mark.parametrize("mode", ["writer_finalize", "outline_writer", "structured_only"])
def test_report_paths_share_output_fields(monkeypatch, mode):
    from searchos.harness import session

    state = _visibility_state()
    if mode == "outline_writer":
        state.outline.sections.append(
            OutlineSection(id="valid", content="OUTLINE_BODY", cited_evidence_ids=["visible"]),
        )
    outputs = {}

    async def finalize(**kwargs):
        return ("WRITER_BODY", "writer_agent_1") if mode == "writer_finalize" else None

    monkeypatch.setattr(session, "_run_writer_finalize", finalize)
    workspace = SimpleNamespace(session_id="report", write_output=outputs.__setitem__)
    events = []
    stream = AnswerStreamEmitter(events.append, stream_prefix="report")
    asyncio.run(session._harness_synthesize(
        workspace=workspace,
        state=state,
        query="test",
        answer_stream=stream,
    ))
    result = json.loads(outputs["result.json"])
    assert result["mode"] == mode
    assert result["answer"] == outputs["report.md"]
    assert result["query"] == "test"
    assert result["evidence_count"] > 0
    assert result["url_citations"]
    assert events[0]["phase"] == "final_answer"
    assert "".join(event.get("delta", "") for event in events) == result["answer"]
    assert ("writer_agent_id" in result) == (mode == "writer_finalize")
    if mode == "writer_finalize":
        assert "WRITER_BODY" in result["answer"]
    elif mode == "outline_writer":
        assert "OUTLINE_BODY" in result["answer"]
