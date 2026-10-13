"""WebSocket route — real-time search progress streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.deps import WORKSPACE_ROOT, session_directory, sessions
from api.state_stream import StateStream

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
        jsonl_files = [ws_path / "trajectory.jsonl"] + [
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
                # Stream trajectory.jsonl (tool calls, steps)
                await _stream_jsonl(ws, ws_path / "trajectory.jsonl", "trajectory", file_positions)

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
    key = str(file_path)
    if not file_path.exists():
        return

    pos = positions.get(key, 0)
    try:

        def read_lines():
            with file_path.open("rb") as stream:
                if stream.seek(0, 2) < pos:
                    stream.seek(0)
                else:
                    stream.seek(pos)
                records = []
                while line := stream.readline():
                    if not line.endswith(b"\n"):
                        break
                    records.append((stream.tell(), line))
                return records

        for end, line in await asyncio.to_thread(read_lines):
            positions[key] = end
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            await ws.send_json(
                {"type": event_prefix, "data": entry, "event_id": f"{event_prefix}:{end}"}
            )

    except Exception:
        pass
