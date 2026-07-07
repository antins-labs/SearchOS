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
    ws = Path(WORKSPACE_ROOT) / session_id
    if not ws.exists():
        raise HTTPException(404, f"Session {session_id} not found")

    state = None
    state_file = ws / "search_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            logger.warning("Failed to parse search_state for %s", session_id)

    answer = ""
    coverage = None
    evidence_count = None
    title = ""
    result_file = ws / "output" / "result.json"
    if result_file.exists():
        try:
            r = json.loads(result_file.read_text(encoding="utf-8", errors="replace"))
            answer = r.get("answer") or ""
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

    return {
        "session_id": session_id,
        "query": title or "(untitled search)",
        "status": status,
        "coverage_score": float(coverage) if coverage is not None else None,
        "evidence_count": int(evidence_count) if evidence_count is not None else None,
        "answer": answer,
        "search_state": state,
        "events": events,
    }


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
