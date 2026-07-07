"""WebSocket route — real-time search progress streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.deps import WORKSPACE_ROOT, sessions

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

    ws_path = Path(WORKSPACE_ROOT) / session_id

    # Track file positions for incremental reads
    file_positions: dict[str, int] = {}
    last_coverage = 0.0
    last_evidence_count = 0
    last_cells_fingerprint = ""

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
                        ws, ws_path / "blackboard" / f"{stream_name}.jsonl",
                        f"blackboard.{stream_name}", file_positions,
                    )

                # Check coverage/evidence changes
                state_file = ws_path / "search_state.json"
                if state_file.exists():
                    try:
                        state = json.loads(state_file.read_text())
                        cmap = state.get("coverage_map", {})
                        cells = cmap.get("cells", {})
                        filled = sum(
                            1 for c in cells.values()
                            if c.get("status") in ("filled", "resolved")
                        )
                        total = len(cells)
                        coverage = filled / total if total > 0 else 0.0
                        cells_fingerprint = json.dumps(
                            cells, sort_keys=True, ensure_ascii=False,
                        )

                        evidence_count = len(state.get("evidence_graph", {}).get("nodes", []))

                        if (
                            coverage != last_coverage
                            or cells_fingerprint != last_cells_fingerprint
                        ):
                            await ws.send_json({
                                "type": "coverage_updated",
                                "coverage": coverage,
                                "filled": filled,
                                "total": total,
                                "cells": cells,
                            })
                            last_coverage = coverage
                            last_cells_fingerprint = cells_fingerprint

                        if evidence_count != last_evidence_count:
                            nodes = state.get("evidence_graph", {}).get("nodes", [])
                            new_nodes = nodes[last_evidence_count:]
                            for node in new_nodes:
                                await ws.send_json({
                                    "type": "evidence_added",
                                    "node": node,
                                })
                            last_evidence_count = evidence_count

                    except (json.JSONDecodeError, KeyError):
                        pass

            # Check if search is done
            if is_done:
                final_status = session["status"]
                if final_status == "completed" and session.get("result"):
                    r = session["result"]
                    await ws.send_json({
                        "type": "search_complete",
                        "coverage": r.coverage_score,
                        "evidence_count": r.evidence_count,
                        "total_queries": r.total_queries,
                        "total_steps": r.total_steps,
                        "elapsed_s": r.elapsed_s,
                        "eval_verdict": r.eval_verdict,
                    })
                elif final_status == "error":
                    await ws.send_json({
                        "type": "search_error",
                        "error": session.get("error", "unknown"),
                    })
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
        with open(file_path, encoding="utf-8") as f:
            f.seek(pos)
            new_data = f.read()
            if not new_data:
                return
            positions[key] = f.tell()

        for line in new_data.strip().split("\n"):
            if not line:
                continue
            try:
                entry = json.loads(line)
                await ws.send_json({
                    "type": event_prefix,
                    "data": entry,
                })
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
