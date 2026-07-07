"""WorkspaceManager: session workspace directory lifecycle + SOCM persistence.

The file system is the persistent medium for all search state. Layout:
  workspace/<session_id>/
    search_state.json   coverage_map.json   plan.md
    evidence/  blackboard/  intermediate/  skills/  agent_logs/  output/
    pages/<page_id>.md + <page_id>.meta.json   trajectory.jsonl

``atomic_update_state`` is the single SOCM write entry point (file lock).
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from searchos.config.settings import settings
from searchos.socm.state import SearchState

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Create, load, and persist workspace for one search session."""

    def __init__(self, root: str | Path, session_id: str | None = None) -> None:
        self._root = Path(root)
        self._session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = self._root / self._session_id
        self._state: SearchState | None = None
        # In-flight extraction-buffer sizes per EvidenceExtractionMiddleware
        # (keyed by id). Read by LoopSensor to avoid declaring a stall while an
        # agent is productively buffering observations it hasn't flushed yet.
        self._extraction_pending: dict[int, int] = {}

    def report_extraction_pending(self, owner: Any, count: int) -> None:
        self._extraction_pending[id(owner)] = max(0, int(count))

    @property
    def extraction_pending_total(self) -> int:
        return sum(self._extraction_pending.values())

    # ---- Lifecycle ----

    def create(self) -> Path:
        """Create the workspace directory tree. Idempotent. ``evidence/`` is
        created lazily (findings go straight into search_state.json)."""
        for sub in [
            settings.blackboard_dir,
            settings.intermediate_dir,
            settings.agent_logs_dir,
            settings.output_dir,
            "skills",
        ]:
            (self._path / sub).mkdir(parents=True, exist_ok=True)
        logger.info("Workspace created: %s", self._path)
        return self._path

    # ---- State persistence ----

    def save_state(self, state: SearchState) -> None:
        self._state = state
        self._write_json_locked("search_state.json", state.model_dump())

    def load_state(self) -> SearchState:
        data = self._read_json("search_state.json")
        self._state = SearchState() if data is None else SearchState.model_validate(data)
        return self._state

    @property
    def state(self) -> SearchState:
        """Always re-read from disk so parallel sub-agents see each other's writes."""
        return self.load_state()

    def atomic_update_state(self, updater: "callable") -> SearchState:
        """Read-modify-write under a file lock (prevents concurrent overwrites).

            def fill_cell(state):
                state.coverage_map.fill("Tesla", "revenue", finding_id="f_abc", ...)
                return state
            ws.atomic_update_state(fill_cell)
        """
        lock_path = self._path / ".state.lock"
        lock_path.touch(exist_ok=True)
        with open(lock_path, "r") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                state = self.load_state()
                state = updater(state)
                self.save_state(state)
                return state
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)

    def save_coverage_map(self) -> None:
        if self._state:
            self._write_json_locked("coverage_map.json", self._state.coverage_map.model_dump())

    # ---- Plan ----

    def save_plan(self, plan_text: str) -> None:
        (self._path / "plan.md").write_text(plan_text, encoding="utf-8")

    def load_plan(self) -> str:
        p = self._path / "plan.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # ---- Evidence ----

    def evidence_dir_for(self, agent_name: str) -> Path:
        d = self._path / settings.evidence_dir / agent_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_evidence(self, agent_name: str, filename: str, content: str) -> Path:
        p = self.evidence_dir_for(agent_name) / filename
        p.write_text(content, encoding="utf-8")
        return p

    # ---- Blackboard ----

    @property
    def blackboard_dir(self) -> Path:
        return self._path / settings.blackboard_dir

    # ---- Pages (fetched raw page content) ----

    @property
    def pages_dir(self) -> Path:
        d = self._path / "pages"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_page(self, page_id: str, url: str, content: str, title: str = "") -> Path:
        """Persist a page body to ``<page_id>.md`` + metadata to
        ``<page_id>.meta.json``. Extension is ``.md`` (not ``.html``) because
        the browser feeds html2text-rendered markdown."""
        body_path = self.pages_dir / f"{page_id}.md"
        meta_path = self.pages_dir / f"{page_id}.meta.json"
        ts = datetime.now().isoformat()

        body_path.write_text(content, encoding="utf-8")
        meta = {
            "page_id": page_id, "url": url, "title": title or "",
            "fetched_at": ts, "size": len(content),
            "content_type": "markdown", "content_path": body_path.name,
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self._update_page_index(page_id, url, title, len(content), ts)
        return body_path

    def _update_page_index(self, page_id: str, url: str, title: str, size: int, ts: str) -> None:
        """Append to pages/index.json (the frontend's page-list aggregator)."""
        index_path = self.pages_dir / "index.json"
        try:
            index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
        except Exception:
            index = {}
        domain = urlparse(url).netloc if url else ""
        path_short = urlparse(url).path[:50] if url else ""
        index[page_id] = {
            "url": url, "domain": domain, "path": path_short,
            "title": title or f"{domain}{path_short}", "size": size, "fetched_at": ts,
        }
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    def read_page(self, page_id: str) -> str:
        """Read a saved page body ('' if missing). Tolerates legacy YAML
        frontmatter from before metadata moved to the sidecar."""
        p = self.pages_dir / f"{page_id}.md"
        if not p.exists():
            return ""
        raw = p.read_text(encoding="utf-8")
        if raw.startswith("---"):
            end = raw.find("\n---\n", 4)
            if end != -1:
                return raw[end + 5:].lstrip("\n")
        return raw

    def read_page_meta(self, page_id: str) -> dict | None:
        p = self.pages_dir / f"{page_id}.meta.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ---- Trajectory / conversation paths ----

    @property
    def trajectory_path(self) -> Path:
        return self._path / settings.trajectory_file

    @property
    def conversation_path(self) -> Path:
        return self._path / settings.conversation_file

    # ---- Intermediate / output ----

    def write_intermediate(self, filename: str, content: str) -> Path:
        p = self._path / settings.intermediate_dir / filename
        p.write_text(content, encoding="utf-8")
        return p

    def write_output(self, filename: str, content: str) -> Path:
        p = self._path / settings.output_dir / filename
        p.write_text(content, encoding="utf-8")
        return p

    # ---- Helpers ----

    def _write_json_locked(self, name: str, data: dict) -> None:
        """Write JSON under a file lock + atomic replace, so lock-less readers
        (frontend, status scripts) never observe a half-written file."""
        p = self._path / name
        content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        lock_path = self._path / f".{name}.lock"
        lock_path.touch(exist_ok=True)
        with open(lock_path, "r") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                tmp = self._path / f".{name}.tmp"
                tmp.write_text(content, encoding="utf-8")
                os.replace(tmp, p)
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)

    def _read_json(self, name: str) -> dict | None:
        p = self._path / name
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    @property
    def path(self) -> Path:
        return self._path

    @property
    def session_id(self) -> str:
        return self._session_id
