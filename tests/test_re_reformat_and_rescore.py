from pathlib import Path

from eval.re_reformat_and_rescore import _load_raw_answer
from searchos.socm import EvidenceNode, ForeignKey, Relation, SearchState


def test_load_raw_answer_can_reexport_search_state(tmp_path: Path) -> None:
    qdir = tmp_path / "ws_test"
    session_dir = qdir / "session"
    session_dir.mkdir(parents=True)
    (qdir / "raw_answer.md").write_text("STALE RAW", encoding="utf-8")

    state = SearchState(intent="test")
    state.coverage_map.add_table(
        "parent", ["key"], primary_key=["key"], entities=["第46届"]
    )
    state.coverage_map.add_table(
        "child",
        ["key", "award", "winner"],
        primary_key=["key", "award"],
        entities=["46|Best Rap Album"],
    )
    state.coverage_map.add_relation(
        Relation(
            from_table="child",
            foreign_key=ForeignKey(
                target_table="parent",
                columns=["key"],
                target_columns=["key"],
            ),
        )
    )
    node = EvidenceNode(
        id="winner",
        table_id="child",
        entity="46|Best Rap Album",
        attribute="winner",
        value="OutKast",
        alignment="full",
    )
    state.evidence_graph.add_node(node)
    state.coverage_map.fill_from_evidence([node])
    (session_dir / "search_state.json").write_text(
        state.model_dump_json(), encoding="utf-8"
    )

    raw = _load_raw_answer(qdir, reexport_search_state=True)

    assert "STALE RAW" not in raw
    assert "Best Rap Album" in raw
    assert "OutKast" in raw


def test_load_raw_answer_returns_empty_for_empty_search_state(tmp_path: Path) -> None:
    qdir = tmp_path / "ws_empty"
    session_dir = qdir / "session"
    session_dir.mkdir(parents=True)
    state = SearchState(intent="test")
    state.coverage_map.add_table(
        "empty", ["key", "value"], primary_key=["key"]
    )
    (session_dir / "search_state.json").write_text(
        state.model_dump_json(), encoding="utf-8"
    )

    assert _load_raw_answer(qdir, reexport_search_state=True) == ""
