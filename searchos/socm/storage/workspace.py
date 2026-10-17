"""WorkspaceManager: session workspace directory lifecycle + SOCM persistence.

The file system is the persistent medium for all search state. Layout:
  workspace/<session_id>/
    search_state.json   plan.md   trajectory.jsonl
    output/   pages/   conversations/   turn_snapshots/
    skills/{packages,bindings,calls,executions,work}/
    extraction_pending/<owner>/completed.json + pending/failed records

Directories are created on first write. Optional evidence, intermediate and
agent log files remain available when their corresponding features write them.

``atomic_update_state`` is the single SOCM write entry point (file lock).
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from searchos.config.settings import settings
from searchos.socm.storage.persistence import read_snapshot
from searchos.socm.state import SearchState

logger = logging.getLogger(__name__)


def new_session_id() -> str:
    """按服务器本地时间排序；随机后缀区分同秒创建的会话。"""
    return f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:12]}"


def resolve_session_path(root: str | Path, session_id: str) -> Path:
    """兼容迁移前的哈希 ID；磁盘只保留带时间戳的真实目录。"""
    root = Path(root).resolve()
    if not session_id or session_id in {".", ".."} or "/" in session_id or "\\" in session_id:
        raise ValueError("Invalid session id")
    path = (root / session_id).resolve()
    if path.parent != root:
        raise ValueError("Invalid session id")
    if not path.exists() and re.fullmatch(r"[0-9a-f]{12}", session_id):
        matches = [candidate for candidate in root.glob(f"*_{session_id}")
                   if re.fullmatch(r"\d{8}_\d{6}_" + session_id, candidate.name)
                   and candidate.is_dir() and candidate.resolve().parent == root]
        if len(matches) > 1:
            raise ValueError("Ambiguous legacy session id")
        if matches:
            path = matches[0].resolve()
    return path


class WorkspaceManager:
    """Create, load, and persist workspace for one search session."""

    def __init__(self, root: str | Path, session_id: str | None = None) -> None:
        self._root = Path(root)
        self._session_id = session_id or new_session_id()
        self._path = resolve_session_path(self._root, self._session_id)
        self._session_id = self._path.name
        self._state: SearchState | None = None
        # In-flight extraction-buffer sizes per ExtractionCoordinator
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
        """创建会话根目录；各功能首次写入时再创建自己的目录。"""
        self._path.mkdir(parents=True, exist_ok=True)
        logger.info("Workspace created: %s", self._path)
        return self._path

    # ---- State persistence ----

    def save_state(self, state: SearchState) -> None:
        self._state = state
        self._write_content_locked("search_state.json", state.model_dump_json())

    def load_state(self) -> SearchState:
        try:
            snapshot = read_snapshot(self._path / "search_state.json")
        except FileNotFoundError:
            self._state = SearchState()
        else:
            self._state = SearchState.model_validate_json(snapshot.content)
        return self._state

    @property
    def state(self) -> SearchState:
        """Always re-read from disk so parallel sub-agents see each other's writes."""
        return self.load_state()

    def atomic_update_state(self, updater: callable) -> SearchState:
        """Read-modify-write under a file lock (prevents concurrent overwrites).

            def fill_cell(state):
                state.coverage_map.fill("Tesla", "revenue", finding_id="f_abc", ...)
                return state
            ws.atomic_update_state(fill_cell)
        """
        lock_path = self._path / ".state.lock"
        lock_path.touch(exist_ok=True)
        with open(lock_path) as lock_fd:
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

    def save_turn_snapshot(
        self,
        query: str,
        state: SearchState,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Persist the completed state for one conversational turn.

        Follow-up runs reuse ``search_state.json``, so that file only reflects
        the latest turn. Snapshot numbering follows successful
        ``task_complete`` events, which keeps interrupted runs from creating
        gaps in the user-visible conversation.
        """
        snapshots_dir = self._path / "turn_snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._path / ".turn_snapshots.lock"
        lock_path.touch(exist_ok=True)

        with lock_path.open() as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                completed_turns = 0
                if self.trajectory_path.exists():
                    for line in self.trajectory_path.read_text(
                        encoding="utf-8", errors="replace",
                    ).splitlines():
                        try:
                            if json.loads(line).get("type") == "task_complete":
                                completed_turns += 1
                        except (json.JSONDecodeError, AttributeError):
                            continue

                existing = [
                    int(path.stem) - 1
                    for path in snapshots_dir.glob("*.json")
                    if path.stem.isdigit()
                ]
                # A branched workspace starts with a copied baseline snapshot
                # but no trajectory. Its first completed run must append V2,
                # not overwrite that baseline as V1.
                turn_index = max(
                    completed_turns - 1,
                    max(existing, default=-1) + 1,
                )

                payload: dict[str, Any] = {
                    "version": 1,
                    "turn_index": turn_index,
                    "query": query,
                    "completed_at": datetime.now().astimezone().isoformat(),
                    "search_state": state.model_dump(),
                }
                if metadata:
                    payload.update(metadata)

                target = snapshots_dir / f"{turn_index + 1:04d}.json"
                tmp = snapshots_dir / f".{target.name}.tmp"
                tmp.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                os.replace(tmp, target)
                return target
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)

    def update_latest_turn_snapshot(
        self,
        state: SearchState,
        metadata: dict[str, Any] | None = None,
    ) -> Path | None:
        """Refresh the latest snapshot after an in-place user edit."""
        snapshots_dir = self._path / "turn_snapshots"
        candidates = sorted(
            path for path in snapshots_dir.glob("*.json")
            if path.stem.isdigit()
        )
        if not candidates:
            return None

        lock_path = self._path / ".turn_snapshots.lock"
        lock_path.touch(exist_ok=True)
        with lock_path.open() as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                target = candidates[-1]
                payload = json.loads(target.read_text(encoding="utf-8"))
                payload["search_state"] = state.model_dump()
                payload["updated_at"] = datetime.now().astimezone().isoformat()
                if metadata:
                    payload.update(metadata)
                tmp = snapshots_dir / f".{target.name}.tmp"
                tmp.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                os.replace(tmp, target)
                return target
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)

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
        return self._path / "pages"

    def write_page(
        self,
        page_id: str,
        url: str,
        content: str,
        title: str = "",
        *,
        source_url: str = "",
        page_metadata: dict | None = None,
    ) -> Path:
        """Persist a page body to ``<page_id>.md`` + metadata to
        ``<page_id>.meta.json``. Extension is ``.md`` (not ``.html``) because
        the browser feeds html2text-rendered markdown."""
        body_path = self.pages_dir / f"{page_id}.md"
        meta_path = self.pages_dir / f"{page_id}.meta.json"
        body_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().isoformat()

        body_path.write_text(content, encoding="utf-8")
        meta = {
            "page_id": page_id, "url": url, "title": title or "",
            "source_url": source_url or url,
            "fetched_at": ts, "size": len(content),
            "content_type": "markdown", "content_path": body_path.name,
            "page_metadata": page_metadata or {},
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
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def write_output(self, filename: str, content: str) -> Path:
        p = self._path / settings.output_dir / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    # ---- Helpers ----

    def _write_json_locked(self, name: str, data: dict) -> None:
        """Write JSON under a file lock + atomic replace, so lock-less readers
        (frontend, status scripts) never observe a half-written file."""
        content = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        self._write_content_locked(name, content)

    def _write_content_locked(self, name: str, content: str) -> None:
        p = self._path / name
        lock_path = self._path / f".{name}.lock"
        lock_path.touch(exist_ok=True)
        with open(lock_path) as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                try:
                    if read_snapshot(p).content == content.encode("utf-8"):
                        return
                except FileNotFoundError:
                    pass
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
