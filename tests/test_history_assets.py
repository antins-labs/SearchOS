"""Research asset metadata and full-text history search regression tests."""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
for path in (str(_REPO), str(_REPO / "web")):
    if path not in sys.path:
        sys.path.insert(0, path)

from api.routes import history


def _workspace(root: Path, session_id: str, *, title: str, answer: str = "") -> Path:
    ws = root / session_id
    (ws / "output").mkdir(parents=True)
    (ws / "search_state.json").write_text(
        json.dumps({
            "intent": title,
            "evidence_graph": {
                "nodes": [{
                    "finding": "The launch date was verified by the regulator",
                    "source_excerpt": "Regulator evidence excerpt",
                    "source": "https://regulator.example/report",
                }],
            },
        }),
        encoding="utf-8",
    )
    (ws / "output" / "result.json").write_text(
        json.dumps({"query": title, "answer": answer, "coverage": 0.75}),
        encoding="utf-8",
    )
    return ws


def test_history_assets_are_backward_compatible(monkeypatch, tmp_path):
    _workspace(tmp_path, "legacy", title="Legacy research")
    monkeypatch.setattr(history, "WORKSPACE_ROOT", str(tmp_path))

    items = asyncio.run(history.list_history())

    assert len(items) == 1
    assert items[0]["project"] == ""
    assert items[0]["tags"] == []
    assert items[0]["favorite"] is False
    assert items[0]["archived"] is False


def test_update_history_assets_normalizes_and_persists(monkeypatch, tmp_path):
    _workspace(tmp_path, "session", title="Market research")
    monkeypatch.setattr(history, "WORKSPACE_ROOT", str(tmp_path))

    response = asyncio.run(history.update_history(
        "session",
        history.HistoryUpdateRequest(
            project="  AI Infrastructure  ",
            tags=[" GPU ", "pricing", "GPU", ""],
            favorite=True,
            archived=True,
        ),
    ))
    items = asyncio.run(history.list_history())

    assert response["project"] == "AI Infrastructure"
    assert response["tags"] == ["GPU", "pricing"]
    assert items[0]["favorite"] is True
    assert items[0]["archived"] is True
    stored = json.loads((tmp_path / "session" / ".research_meta.json").read_text())
    assert stored == {
        "project": "AI Infrastructure",
        "tags": ["GPU", "pricing"],
        "favorite": True,
        "archived": True,
    }


def test_history_full_text_search_covers_answers_and_evidence(monkeypatch, tmp_path):
    _workspace(tmp_path, "alpha", title="Chip vendors", answer="Includes H100 pricing analysis")
    _workspace(tmp_path, "beta", title="Launch timeline", answer="No pricing data")
    monkeypatch.setattr(history, "WORKSPACE_ROOT", str(tmp_path))

    by_answer = asyncio.run(history.list_history(q="H100 pricing"))
    by_evidence = asyncio.run(history.list_history(q="regulator excerpt"))

    assert [item["session_id"] for item in by_answer] == ["alpha"]
    assert {item["session_id"] for item in by_evidence} == {"alpha", "beta"}


def test_history_asset_filters_can_select_projects_favorites_and_archive(monkeypatch, tmp_path):
    _workspace(tmp_path, "one", title="One")
    _workspace(tmp_path, "two", title="Two")
    monkeypatch.setattr(history, "WORKSPACE_ROOT", str(tmp_path))
    asyncio.run(history.update_history(
        "one",
        history.HistoryUpdateRequest(
            project="Watchlist",
            tags=["weekly"],
            favorite=True,
            archived=True,
        ),
    ))

    favorites = asyncio.run(history.list_history(favorite=True))
    archived = asyncio.run(history.list_history(archived=True))
    project = asyncio.run(history.list_history(project="Watchlist", tags=["weekly"]))

    assert [item["session_id"] for item in favorites] == ["one"]
    assert [item["session_id"] for item in archived] == ["one"]
    assert [item["session_id"] for item in project] == ["one"]
