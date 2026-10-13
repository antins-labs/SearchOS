"""Hybrid 表格填充契约与最终交付回归。"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))


def test_committed_answer_precedes_progress_message(tmp_path, monkeypatch):
    from api.routes import search
    ws = tmp_path / "case"
    (ws / "output").mkdir(parents=True)
    (ws / "output/result.json").write_text(json.dumps({"answer": "Supported final answer"}))
    monkeypatch.setattr(search, "WORKSPACE_ROOT", tmp_path)
    result = SimpleNamespace(final_messages=[{"role": "ai", "content": "I will now write the answer."}])
    assert search._read_answer("case", result) == "Supported final answer"
    (ws / "output/result.json").write_text(json.dumps({"answer": ""}))
    assert search._read_answer("case", result) == ""


@pytest.mark.asyncio
async def test_running_history_does_not_promote_tool_preamble_to_answer(tmp_path, monkeypatch):
    from api.routes import history

    workspace = tmp_path / "running-case"
    (workspace / "conversations" / "snapshots").mkdir(parents=True)
    (workspace / "search_state.json").write_text(
        json.dumps({"intent": "Research a topic"}), encoding="utf-8",
    )
    (workspace / "conversations" / "snapshots" / "orchestrator.json").write_text(json.dumps({
        "messages": [
            {"role": "user", "content": "Research a topic"},
            {"role": "assistant", "content": "I created the schema; now I will search."},
            {"role": "tool_call", "tool_name": "enqueue_tasks", "content": "{}"},
            {"role": "tool_result", "tool_name": "enqueue_tasks", "content": "queued"},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(history, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(history, "sessions", {"running-case": {"status": "running"}})

    loaded = await history.load_history("running-case")

    assert loaded["status"] == "running"
    assert loaded["answer"] == ""
    assert loaded["turns"] == []


def test_hybrid_schema_does_not_require_separate_table_tasks():
    from searchos.socm import SearchState
    from searchos.socm.frontier import FrontierTask
    from searchos.tools.tasks import _empty_table_warning
    state = SearchState(research_mode="findings", source_scope={"mode": "hybrid"})
    state.coverage_map.add_table("items", attributes=["Name", "Year"], primary_key=["Name"])
    state.coverage_map.add_entity("Alpha", table_id="items")
    state.frontier.add(FrontierTask(id="read", question="Read source", result_mode="findings"))
    warning = _empty_table_warning(state)
    assert warning is None
    state.frontier.add(FrontierTask(id="fill", question="Fill attributes", result_mode="table", table_id="items"))
    assert _empty_table_warning(state) is None


def test_history_turn_uses_committed_answer_only_for_matching_query(tmp_path):
    from searchos.harness.telemetry.conversation_context import conversation_turns
    (tmp_path / "conversations" / "snapshots").mkdir(parents=True)
    (tmp_path / "output").mkdir()
    (tmp_path / "conversations/snapshots/orchestrator.json").write_text(json.dumps({"messages": [
        {"role": "user", "content": "Compare sources"},
        {"role": "assistant", "content": "I will now write the answer."},
    ]}))
    result = tmp_path / "output/result.json"
    result.write_text(json.dumps({"query": "Compare sources", "answer": "Supported comparison"}))
    assert conversation_turns(tmp_path)[0]["answer"] == "Supported comparison"
    result.write_text(json.dumps({"query": "Different question", "answer": "Unrelated answer"}))
    assert conversation_turns(tmp_path)[0]["answer"] == "I will now write the answer."
