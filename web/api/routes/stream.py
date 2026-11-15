"""WebSocket route — real-time search progress streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.deps import WORKSPACE_ROOT, session_directory, sessions
from api.research.events import StateStream, file_events, report_journal, timeline_events

logger = logging.getLogger(__name__)
router = APIRouter()

# Poll interval for file changes (seconds)
POLL_INTERVAL = 0.5


@router.websocket("/api/ws/{session_id}")
async def search_stream(ws: WebSocket, session_id: str):
    """Stream real-time updates for a search session.

    Polls workspace files for changes and pushes events to the client.
    Streams: trajectory.jsonl, blackboard/*, search_state.json, coverage_map.json
    """
    await ws.accept()
    logger.info("WebSocket connected: session=%s", session_id)

    ws_path = session_directory(WORKSPACE_ROOT, session_id)
    session_id = ws_path.name

    # Track file positions for incremental reads
    file_positions: dict[str, int] = {}
    state_stream = StateStream()

    # ?tail=1 — start at the current end of every stream instead of replaying
    # from the top. Used by follow-up runs, which reuse the prior session's
    # workspace: the client only wants this turn's events.
    if ws.query_params.get("tail") in ("1", "true") and ws_path.exists():
        jsonl_files = [ws_path / "trajectory.jsonl", report_journal(ws_path)] + [
            ws_path / "blackboard" / f"{name}.jsonl"
            for name in ("progress", "announcements", "claims")
        ]
        for f in jsonl_files:
            if f.exists():
                file_positions[str(f)] = f.stat().st_size

    try:
        while True:
            session = sessions.get(session_id)
            is_done = session and session["status"] in ("completed", "error")

            if ws_path.exists():
                for event in await asyncio.to_thread(timeline_events, ws_path, file_positions):
                    await ws.send_json(event)

                # Stream blackboard
                for stream_name in ("progress", "announcements", "claims"):
                    await _stream_jsonl(
                        ws,
                        ws_path / "blackboard" / f"{stream_name}.jsonl",
                        f"blackboard.{stream_name}",
                        file_positions,
                    )

                # No parsing or serialization when the durable version has not changed.
                try:
                    event = await asyncio.to_thread(
                        state_stream.event, ws_path / "search_state.json"
                    )
                    if event is not None:
                        await ws.send_json(event)
                        for node in state_stream.new_evidence:
                            await ws.send_json(
                                {
                                    "type": "evidence_added",
                                    "node": node,
                                    "event_id": f"evidence:{node['id']}",
                                }
                            )
                except (json.JSONDecodeError, FileNotFoundError):
                    pass

            # Check if search is done
            if is_done:
                final_status = session["status"]
                if final_status == "completed" and session.get("result"):
                    r = session["result"]
                    await ws.send_json(
                        {
                            "type": "search_complete",
                            "coverage": r.coverage_score,
                            "evidence_count": r.evidence_count,
                            "total_queries": r.total_queries,
                            "total_steps": r.total_steps,
                            "skill_execution_count": r.skill_execution_count,
                            "elapsed_s": r.elapsed_s,
                            "eval_verdict": r.eval_verdict,
                        }
                    )
                elif final_status == "error":
                    await ws.send_json(
                        {
                            "type": "search_error",
                            "error": session.get("error", "unknown"),
                        }
                    )
                break

            await asyncio.sleep(POLL_INTERVAL)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    except Exception:
        logger.error("WebSocket error: session=%s", session_id, exc_info=True)


async def _stream_jsonl(
    ws: WebSocket,
    file_path: Path,
    event_prefix: str,
    positions: dict[str, int],
) -> None:
    """Read new lines from a JSONL file and send as WebSocket events."""
    for event in await asyncio.to_thread(list, file_events(file_path, event_prefix, positions)):
        await ws.send_json(event)
