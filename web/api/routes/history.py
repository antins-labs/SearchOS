"""History routes — durable session history read straight from workspace dirs.

The in-memory `sessions` registry is lost on API restart, but every run leaves a
workspace dir on disk. These read-only endpoints list those dirs and load any
past session (including CLI runs) so the frontend can show real history.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import WORKSPACE_ROOT, sessions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_INTENT_RE = re.compile(r'"intent"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _read_intent_fast(state_file: Path) -> str:
    """Pull `intent` from the head of search_state.json without loading the
    whole (possibly multi-MB) file."""
    try:
        head = state_file.read_text(encoding="utf-8", errors="replace")[:4096]
    except Exception:
        return ""
    m = _INTENT_RE.search(head)
    if not m:
        return ""
    try:
        return json.loads(f'"{m.group(1)}"')
    except Exception:
        return m.group(1)


def last_ai_text(messages: list[dict[str, Any]]) -> str:
    """The last AI/assistant text message — the orchestrator's closing answer
    (mirrors the TUI's _extract_answer)."""
    for msg in reversed(messages or []):
        if msg.get("role") not in ("ai", "assistant"):
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            parts = [b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
            content = "\n".join(p for p in parts if p)
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def orchestrator_final_text(ws: Path) -> str:
    """The orchestrator's last AI message from the durable per-agent
    conversation log (conversations/orchestrator.json)."""
    try:
        conv = json.loads(
            (ws / "conversations" / "orchestrator.json")
            .read_text(encoding="utf-8", errors="replace"),
        )
        return last_ai_text(conv.get("messages", []))
    except Exception:
        return ""


def _safe_ws(session_id: str) -> Path:
    """Resolve a workspace dir for a session id, refusing path traversal."""
    root = Path(WORKSPACE_ROOT).resolve()
    ws = (root / session_id).resolve()
    if ws.parent != root:
        raise HTTPException(400, "Invalid session id")
    return ws


def _custom_title(ws: Path) -> str:
    f = ws / ".display_title"
    if f.exists():
        try:
            return f.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
    return ""


def _load_turn_snapshots(ws: Path) -> dict[int, dict[str, Any]]:
    """Load valid versioned turn snapshots, ignoring corrupt/unknown files."""
    snapshots_dir = ws / "turn_snapshots"
    if not snapshots_dir.exists():
        return {}

    snapshots: dict[int, dict[str, Any]] = {}
    for path in sorted(snapshots_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            turn_index = payload.get("turn_index")
            if (
                payload.get("version") != 1
                or not isinstance(turn_index, int)
                or turn_index < 0
                or not isinstance(payload.get("search_state"), dict)
            ):
                continue
            snapshots[turn_index] = payload
        except Exception:
            logger.warning("Failed to parse turn snapshot %s", path)
    return snapshots


def _load_turn_resources(ws: Path) -> dict[int, dict[str, Any]]:
    """Recover per-turn resource totals from durable task_complete events."""
    trajectory = ws / "trajectory.jsonl"
    if not trajectory.exists():
        return {}
    resources: dict[int, dict[str, Any]] = {}
    turn_index = 0
    for line in trajectory.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "task_complete":
            continue
        resources[turn_index] = {
            key: record.get(key)
            for key in (
                "elapsed_s", "total_queries", "total_steps", "tool_counts",
                "token_usage", "token_phases", "model_distribution", "timestamp",
            )
            if record.get(key) is not None
        }
        turn_index += 1
    return resources


def _trajectory_records_for_turn(
    ws: Path,
    turn_index: int,
    turn_count: int,
) -> list[dict[str, Any]]:
    """Return the trajectory segment aligned to one reconstructed turn."""
    trajectory = ws / "trajectory.jsonl"
    if not trajectory.exists() or turn_count <= 0:
        return []

    segments: list[list[dict[str, Any]]] = []
    for line in trajectory.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("type") == "task_start" or not segments:
            segments.append([])
        segments[-1].append(record)

    segment_index = len(segments) - (turn_count - turn_index)
    if segment_index < 0 or segment_index >= len(segments):
        return []
    if turn_index == 0:
        return [record for segment in segments[:segment_index + 1] for record in segment]
    return segments[segment_index]


def _write_branch_trajectory(
    source_ws: Path,
    branch_ws: Path,
    *,
    source_turn_index: int,
    source_turn_count: int,
    branch_id: str,
) -> int:
    records = _trajectory_records_for_turn(
        source_ws,
        source_turn_index,
        source_turn_count,
    )
    if not records:
        return 0
    rewritten = []
    for record in records:
        copied = dict(record)
        if "session_id" in copied:
            copied["session_id"] = branch_id
        rewritten.append(copied)
    (branch_ws / "trajectory.jsonl").write_text(
        "\n".join(
            json.dumps(record, ensure_ascii=False, default=str)
            for record in rewritten
        ) + "\n",
        encoding="utf-8",
    )
    return len(rewritten)


def _turn_views(
    turns: list[dict[str, Any]],
    snapshots: dict[int, dict[str, Any]],
    *,
    latest_state: dict[str, Any] | None,
    latest_coverage: float | None,
    latest_evidence_count: int | None,
    resources: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach the state that belongs to each reconstructed dialogue turn.

    Legacy workspaces have no snapshots. Their final turn may safely use the
    current ``search_state.json``; earlier turns are explicitly unavailable so
    clients never mistake the latest table/evidence for historical state.
    """
    views: list[dict[str, Any]] = []
    last_index = len(turns) - 1
    resources = resources or {}
    for index, turn in enumerate(turns):
        view = dict(turn)
        snapshot = snapshots.get(index)
        resource = resources.get(index, {})
        if snapshot is not None:
            view.update({
                "search_state": snapshot["search_state"],
                "state_source": "snapshot",
                "coverage_score": snapshot.get("coverage_score"),
                "evidence_count": snapshot.get("evidence_count"),
                "completed_at": snapshot.get("completed_at") or resource.get("timestamp"),
            })
        elif index == last_index and latest_state is not None:
            view.update({
                "search_state": latest_state,
                "state_source": "latest",
                "coverage_score": latest_coverage,
                "evidence_count": latest_evidence_count,
                "completed_at": resource.get("timestamp"),
            })
        else:
            view.update({
                "search_state": None,
                "state_source": "unavailable",
                "coverage_score": None,
                "evidence_count": None,
                "completed_at": resource.get("timestamp"),
            })
        for key in (
            "elapsed_s", "total_queries", "total_steps", "tool_counts",
            "token_usage", "token_phases", "model_distribution",
        ):
            value = (
                snapshot.get(key)
                if snapshot and snapshot.get(key) is not None
                else resource.get(key)
            )
            view[key] = value
        views.append(view)
    return views


def _session_meta(ws: Path) -> dict[str, Any] | None:
    sid = ws.name
    state_file = ws / "search_state.json"
    result_file = ws / "output" / "result.json"
    if not state_file.exists() and not result_file.exists():
        return None

    title = _custom_title(ws)
    coverage = None
    if result_file.exists():
        try:
            r = json.loads(result_file.read_text(encoding="utf-8", errors="replace"))
            title = title or r.get("query") or ""
            coverage = r.get("coverage")
        except Exception:
            pass
    if not title:
        title = _read_intent_fast(state_file)

    mem = sessions.get(sid)
    if mem and mem.get("status") == "running":
        status = "running"
    elif result_file.exists():
        status = "completed"
    else:
        status = "incomplete"

    return {
        "session_id": sid,
        "title": title or "(untitled search)",
        "status": status,
        "coverage_score": coverage,
        "updated_at": ws.stat().st_mtime,
    }


@router.get("/history")
async def list_history():
    """List all past sessions on disk, newest first."""
    root = Path(WORKSPACE_ROOT)
    if not root.exists():
        return []
    out = []
    for ws in root.iterdir():
        if not ws.is_dir():
            continue
        meta = _session_meta(ws)
        if meta:
            out.append(meta)
    out.sort(key=lambda m: m["updated_at"], reverse=True)
    return out


@router.get("/history/{session_id}")
async def load_history(session_id: str):
    """Load a full past session from its workspace: state + answer + trajectory."""
    ws = _safe_ws(session_id)
    if not ws.exists():
        raise HTTPException(404, f"Session {session_id} not found")

    state = None
    state_file = ws / "search_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            logger.warning("Failed to parse search_state for %s", session_id)

    # The displayed answer is the orchestrator's closing AI message; the
    # writer's report / result.json answer are fallbacks only.
    answer = orchestrator_final_text(ws)
    coverage = None
    evidence_count = None
    title = ""
    result_file = ws / "output" / "result.json"
    if result_file.exists():
        try:
            r = json.loads(result_file.read_text(encoding="utf-8", errors="replace"))
            answer = answer or r.get("answer") or ""
            coverage = r.get("coverage")
            evidence_count = r.get("evidence_count")
            title = r.get("query") or ""
        except Exception:
            pass
    if not answer:
        report = ws / "output" / "report.md"
        if report.exists():
            answer = report.read_text(encoding="utf-8", errors="replace")
    custom = _custom_title(ws)
    if custom:
        title = custom
    if not title:
        title = _read_intent_fast(state_file)

    # Replay the full trajectory in the same envelope the WebSocket uses.
    events: list[dict[str, Any]] = []
    traj = ws / "trajectory.jsonl"
    if traj.exists():
        for line in traj.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append({"type": "trajectory", "data": json.loads(line)})
            except json.JSONDecodeError:
                pass

    mem = sessions.get(session_id)
    status = "running" if (mem and mem.get("status") == "running") else (
        "completed" if result_file.exists() else "incomplete"
    )

    # Full user↔AI dialogue so a reload shows every turn, not title + last answer.
    from searchos.harness.telemetry.conversation_context import conversation_turns
    turns = _turn_views(
        conversation_turns(ws),
        _load_turn_snapshots(ws),
        latest_state=state,
        latest_coverage=float(coverage) if coverage is not None else None,
        latest_evidence_count=int(evidence_count) if evidence_count is not None else None,
        resources=_load_turn_resources(ws),
    )

    return {
        "session_id": session_id,
        "query": title or "(untitled search)",
        "status": status,
        "turns": turns,
        "coverage_score": float(coverage) if coverage is not None else None,
        "evidence_count": int(evidence_count) if evidence_count is not None else None,
        "answer": answer,
        "search_state": state,
        "events": events,
    }


class BranchResponse(BaseModel):
    session_id: str
    source_session_id: str
    source_turn_index: int
    status: str = "ready"


def _write_branch_conversation(ws: Path, query: str, answer: str) -> None:
    """Seed a branch with one durable dialogue turn for snapshot alignment."""
    timestamp = datetime.now(UTC).isoformat()
    messages = [
        {
            "timestamp": timestamp,
            "step_index": 0,
            "agent_name": "orchestrator",
            "parent_agent": "",
            "role": "user",
            "content": query,
            "reasoning": "",
            "tool_name": "",
            "tool_call_id": "",
            "metadata": {},
        },
        {
            "timestamp": timestamp,
            "step_index": 1,
            "agent_name": "orchestrator",
            "parent_agent": "",
            "role": "assistant",
            "content": answer or "This version contains a research snapshot without a text answer.",
            "reasoning": "",
            "tool_name": "",
            "tool_call_id": "",
            "metadata": {},
        },
    ]
    conversations = ws / "conversations"
    conversations.mkdir(parents=True, exist_ok=True)
    (conversations / "orchestrator.json").write_text(
        json.dumps({
            "agent_name": "orchestrator",
            "agent_type": "orchestrator",
            "parent": "",
            "task": query,
            "system_prompt": "",
            "messages": messages,
            "children": [],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@router.post(
    "/history/{session_id}/turns/{turn_index}/branch",
    response_model=BranchResponse,
)
async def branch_history_turn(session_id: str, turn_index: int):
    """Copy one historical turn into a new, independently editable session."""
    from searchos.harness.telemetry.conversation_context import conversation_turns
    from searchos.socm.state import SearchState
    from searchos.socm.workspace import WorkspaceManager

    source_ws = _safe_ws(session_id)
    if not source_ws.exists():
        raise HTTPException(404, f"Session {session_id} not found")

    turns = conversation_turns(source_ws)
    if not turns and turn_index == 0:
        fallback_answer = orchestrator_final_text(source_ws)
        result_file = source_ws / "output" / "result.json"
        if result_file.exists():
            try:
                result = json.loads(result_file.read_text(encoding="utf-8"))
                fallback_answer = fallback_answer or str(result.get("answer") or "")
            except Exception:
                pass
        report_file = source_ws / "output" / "report.md"
        if not fallback_answer and report_file.exists():
            fallback_answer = report_file.read_text(encoding="utf-8", errors="replace")
        turns = [{
            "query": _custom_title(source_ws) or _read_intent_fast(source_ws / "search_state.json"),
            "answer": fallback_answer,
            "steers": [],
        }]
    if turn_index < 0 or turn_index >= len(turns):
        raise HTTPException(404, f"Turn {turn_index + 1} not found")

    snapshots = _load_turn_snapshots(source_ws)
    snapshot = snapshots.get(turn_index)
    state_data = snapshot.get("search_state") if snapshot else None
    if state_data is None and turn_index == len(turns) - 1:
        try:
            state_data = json.loads((source_ws / "search_state.json").read_text(encoding="utf-8"))
        except Exception:
            state_data = None
    if not isinstance(state_data, dict):
        raise HTTPException(409, "This turn has no restorable research snapshot")

    try:
        state = SearchState.model_validate(state_data)
    except Exception as exc:
        logger.warning(
            "Could not validate branch state for %s turn %s",
            session_id,
            turn_index,
            exc_info=True,
        )
        raise HTTPException(409, "This turn's research snapshot is invalid") from exc

    root = Path(WORKSPACE_ROOT)
    while True:
        branch_id = uuid.uuid4().hex[:12]
        branch_ws = root / branch_id
        if not branch_ws.exists():
            break

    workspace = WorkspaceManager(root, branch_id)
    workspace.create()
    workspace.save_state(state)

    source_turn = turns[turn_index]
    query = str(source_turn.get("query") or state.intent or "Research version")
    answer = str(source_turn.get("answer") or "")
    _write_branch_conversation(branch_ws, query, answer)
    copied_event_count = _write_branch_trajectory(
        source_ws,
        branch_ws,
        source_turn_index=turn_index,
        source_turn_count=len(turns),
        branch_id=branch_id,
    )
    (branch_ws / ".display_title").write_text(f"{query} · branch", encoding="utf-8")
    origin = {
        "source_session_id": session_id,
        "source_turn_index": turn_index,
        "copied_event_count": copied_event_count,
        "created_at": datetime.now(UTC).isoformat(),
    }
    (branch_ws / ".branch_origin.json").write_text(
        json.dumps(origin, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    workspace.save_turn_snapshot(
        query,
        state,
        {
            "coverage_score": (
                snapshot.get("coverage_score")
                if snapshot else state.coverage_map.coverage_score
            ),
            "evidence_count": (
                snapshot.get("evidence_count")
                if snapshot else state.evidence_graph.node_count
            ),
            "branched_from": origin,
        },
    )

    return BranchResponse(
        session_id=branch_id,
        source_session_id=session_id,
        source_turn_index=turn_index,
    )


class RenameRequest(BaseModel):
    title: str


@router.patch("/history/{session_id}")
async def rename_history(session_id: str, req: RenameRequest):
    """Set a custom display title (stored as a .display_title file)."""
    ws = _safe_ws(session_id)
    if not ws.exists():
        raise HTTPException(404, f"Session {session_id} not found")
    title = req.title.strip()
    f = ws / ".display_title"
    if title:
        f.write_text(title, encoding="utf-8")
    elif f.exists():
        f.unlink()  # empty title → revert to the original
    return {"ok": True, "session_id": session_id, "title": title}


@router.delete("/history/{session_id}")
async def delete_history(session_id: str):
    """Delete a session's workspace directory (irreversible)."""
    ws = _safe_ws(session_id)
    if not ws.exists():
        raise HTTPException(404, f"Session {session_id} not found")
    shutil.rmtree(ws)
    sessions.pop(session_id, None)
    return {"ok": True, "session_id": session_id}
