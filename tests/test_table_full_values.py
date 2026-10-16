"""完整表格值、摘要与来源引用不得混用。"""

import json
from types import SimpleNamespace

import pytest

from searchos.socm import CellEvidenceBinding, EvidenceNode, SearchState
from searchos.socm.coverage import bind_cell_evidence, clear_cell_evidence, commit_evidence
from searchos.socm.workspace import WorkspaceManager
from searchos.tools import schema

LONG_URL = "https://news.example.org/articles/" + "Ab3_-" * 60 + "?edition=us&lang=en"


def news_state(value=LONG_URL):
    state = SearchState()
    state.coverage_map.add_table(
        "news", ["headline", "source"], primary_key=["headline"], entities=["Alpha"]
    )
    commit_evidence(
        state,
        [
            EvidenceNode(
                id="article",
                table_id="news",
                entity="Alpha",
                attribute="source",
                value=value,
                finding="Alpha article",
                alignment="full",
                source=LONG_URL,
            )
        ],
    )
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_inspect_and_serialized_table_preserve_complete_values(tmp_path, monkeypatch, legacy):
    workspace = WorkspaceManager(tmp_path, "full-values")
    workspace.create()
    state = news_state()
    raw = state.model_dump()
    if legacy:
        for cell in raw["coverage_map"]["cells"].values():
            cell.pop("full_value", None)
    (workspace.path / "search_state.json").write_text(json.dumps(raw))
    monkeypatch.setattr(schema, "_orch_ctx", lambda: SimpleNamespace(workspace=workspace))
    result = json.loads(await schema.inspect_table.ainvoke({"table_id": "news"}))
    assert result["values"]["Alpha"]["source"] == LONG_URL
    assert result["citations"]["Alpha"]["source"] == "evidence:article"
    cell = workspace.load_state().coverage_map.cells["news/Alpha.source"]
    assert cell.value == LONG_URL
    assert cell.model_dump()["value"] == LONG_URL
    assert len(cell.display_hint) <= 120
    no_values = json.loads(await schema.inspect_table.ainvoke({"with_values": False}))
    assert "values" not in no_values and "citations" not in no_values


def test_projection_and_legacy_roundtrip_use_cell_value_not_original_fact():
    state = news_state("A long narrative. " * 30)
    bind_cell_evidence(
        state,
        [
            (
                "news/Alpha.source",
                CellEvidenceBinding(
                    evidence_id="article",
                    value=LONG_URL,
                ),
            )
        ],
        overwrite=True,
    )
    raw = state.model_dump()
    raw["coverage_map"]["cells"]["news/Alpha.source"].pop("full_value", None)
    loaded = SearchState.model_validate(raw)
    assert loaded.coverage_map.cells["news/Alpha.source"].value == LONG_URL
    assert loaded.evidence_graph.get_node("article").value != LONG_URL
    clear_cell_evidence(loaded, "news", "Alpha", "source")
    assert loaded.coverage_map.cells["news/Alpha.source"].value == ""


def test_full_text_preserves_winner_and_primary_key_rename():
    text = "A detailed explanation. " * 40
    state = news_state(text)
    commit_evidence(
        state,
        [
            EvidenceNode(
                id="weaker",
                table_id="news",
                entity="Alpha",
                attribute="source",
                value="weaker",
                finding="weaker",
                alignment="loose",
                source="https://example.org/other",
            )
        ],
    )
    assert state.coverage_map.cells["news/Alpha.source"].value == text
    state.coverage_map.edit_entity("Alpha", "Beta", table_id="news")
    assert state.coverage_map.cells["news/Beta.headline"].value == "Beta"


def test_table_citation_resolves_opaque_url_without_retyping():
    from searchos.socm.provenance import resolve_answer_citations

    answer, issues = resolve_answer_citations(
        "[Article](evidence:article)", news_state().evidence_graph.nodes
    )
    assert answer == f"[Article]({LONG_URL})"
    assert issues == []


@pytest.mark.parametrize("invalid", ["rejected", "missing", "out_of_scope"])
def test_legacy_recovery_does_not_restore_unavailable_evidence(invalid):
    raw = news_state().model_dump()
    raw["coverage_map"]["cells"]["news/Alpha.source"].pop("full_value", None)
    if invalid == "rejected":
        raw["coverage_map"]["evidence_bindings"]["news/Alpha.source"] = [
            {"evidence_id": "article", "value": LONG_URL, "status": "rejected"}
        ]
    elif invalid == "missing":
        raw["evidence_graph"]["nodes"] = []
    else:
        raw["source_scope"] = {"mode": "local"}
    assert SearchState.model_validate(raw).coverage_map.cells["news/Alpha.source"].value != LONG_URL
