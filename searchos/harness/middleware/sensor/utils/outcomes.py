"""读取工具的结构化结果；正文仅兼容旧工具，不用内容长度推断成功。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolOutcome:
    failed: bool
    empty: bool
    reading_key: str = ""


def tool_outcome(name: str, result: Any, args: Any = None) -> ToolOutcome:
    artifact = getattr(result, "artifact", None)
    artifact = artifact if isinstance(artifact, dict) else {}
    content = getattr(result, "content", result)
    payload = content if isinstance(content, dict) else {}
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            payload = parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            pass
    details = artifact.get("outcome", artifact.get("execution", artifact))
    details = details if isinstance(details, dict) else {}
    status = details.get("status", payload.get("status", getattr(result, "status", "")))
    explicit_status = (
        "status" in details
        or "status" in payload
        or "status" in getattr(result, "model_fields_set", set())
    )
    failed = (
        getattr(result, "status", "") == "error"
        or status in {"error", "failed", "failure", "blocked", "cancelled", "timed_out"}
        or details.get("success", payload.get("success")) is False
        or bool(details.get("error", payload.get("error")))
    )
    # Legacy errors use a leading marker. A paper mentioning "error" is valid content.
    text = content if isinstance(content, str) else ""
    if not explicit_status and re.match(r"^\s*(?:error\b|\[error\]|HTTP [45]\d\d\b)", text, re.I):
        failed = True
    from searchos.tools.simple_browser import FETCH_ERROR_SENTINEL

    failed = failed or FETCH_ERROR_SENTINEL in text
    empty = status in {"empty", "no_results"} or details.get("empty") is True
    collections = [payload[k] for k in ("results", "records", "papers", "matches") if k in payload]
    if collections and all(isinstance(value, list) and not value for value in collections):
        empty = True
    if not content or (isinstance(content, str) and not content.strip()):
        empty = True
    if failed or empty:
        return ToolOutcome(failed, empty)

    source = artifact.get("page_source") or artifact.get("local_source_metadata")
    key = ""
    if isinstance(source, dict) and name in {"open", "find", "local_open", "local_find", "read_visual"}:
        identity = {
            k: v
            for k, v in source.items()
            if k
            in {
                "source_url",
                "view_url",
                "ref_id",
                "document_id",
                "viewport",
                "start",
                "end",
                "start_char",
                "end_char",
                "text_hash",
                "content_hash",
                "text_range",
                "source_revision",
                "representation_id",
                "excerpt_hash",
            }
        }
        if identity:
            key = json.dumps(identity, sort_keys=True, default=str)
    elif name in {"open", "find", "local_open", "local_find"}:
        # Stable legacy identity ignores titles and display-only call/page numbers.
        match = re.search(r"^URL:\s*((?:https?://|skill://)\S+)", text, re.M)
        local = text.startswith(("[Now viewing local source]", "[Local source matches]"))
        if match or local:
            params = args if isinstance(args, dict) else {}
            source_id = match.group(1) if match else params.get("ref_id", params.get("path", ""))
            window = re.search(r"viewing lines \[([^]]+)\]", text)
            coordinates = (
                window.group(1)
                if window
                else {
                    k: params[k]
                    for k in ("loc", "start", "end", "num_lines", "pattern")
                    if k in params
                }
            )
            key = json.dumps([source_id, coordinates], sort_keys=True, default=str)
    return ToolOutcome(False, False, hashlib.sha256(key.encode()).hexdigest() if key else "")
