"""Evidence Extraction 持久化 seam 及其 adapters。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from searchos.socm import SearchState


class EvidenceStore(Protocol):
    """Evidence Extraction 所需的最小持久化 Interface。"""

    def load_state(self) -> SearchState: ...

    def atomic_update_state(self, updater: Callable[[SearchState], SearchState]) -> SearchState: ...

    def report_extraction_pending(self, owner: Any, count: int) -> None: ...


class WorkspaceEvidenceStore:
    """使用 WorkspaceManager 文件锁和 search_state.json 的生产 adapter。"""

    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace

    def observation_journal(self, owner: str):
        # WorkspaceManager owns this durable session path. Lightweight test
        # workspaces without a filesystem retain in-memory semantics.
        root = getattr(self.workspace, "_path", None)
        return _ObservationJournal(root, owner) if root is not None else None

    def load_state(self) -> SearchState:
        return self.workspace.load_state()

    def atomic_update_state(self, updater: Callable[[SearchState], SearchState]) -> SearchState:
        return self.workspace.atomic_update_state(updater)

    def report_extraction_pending(self, owner: Any, count: int) -> None:
        self.workspace.report_extraction_pending(owner, count)

    def report_extraction_rejections(self, owner: Any, counts: dict[str, int]) -> None:
        report = getattr(self.workspace, "report_extraction_rejections", None)
        if callable(report):
            report(owner, counts)


class InMemoryEvidenceStore:
    """无需 Agent Middleware 或文件系统的测试 adapter。"""

    def __init__(self, state: SearchState | None = None) -> None:
        self.state = state or SearchState()
        self.pending_by_owner: dict[int, int] = {}
        self.rejection_counts: dict[str, int] = {}

    def load_state(self) -> SearchState:
        return self.state.model_copy(deep=True)

    def atomic_update_state(self, updater: Callable[[SearchState], SearchState]) -> SearchState:
        self.state = updater(self.state.model_copy(deep=True))
        return self.state.model_copy(deep=True)

    def report_extraction_pending(self, owner: Any, count: int) -> None:
        self.pending_by_owner[id(owner)] = max(0, int(count))

    def report_extraction_rejections(self, owner: Any, counts: dict[str, int]) -> None:
        for reason, count in (counts or {}).items():
            key = str(reason or "unknown")
            self.rejection_counts[key] = self.rejection_counts.get(key, 0) + max(0, int(count))


class _ObservationJournal:
    """任务内的抽取日志；原子发布单条记录，不混入已提交 SourceObservation。

    调度方须保证同一任务仅有一个活跃协调器。不同任务与抽取策略隔离；
    重建协调器可恢复 pending/failed；done 进入完成索引；abandoned 为终态，不重放。
    """

    _ACTIVE = frozenset({"pending", "failed"})

    def __init__(self, root: Any, owner: str) -> None:
        self.path = Path(root) / "extraction_pending" / hashlib.sha256(owner.encode()).hexdigest()
        self._completed: set[str] | None = None
        self._abandoned: set[str] | None = None

    def load(self) -> list[dict[str, Any]]:
        index_path = self.path / "completed.json"
        completed: set[str] = set()
        abandoned: set[str] = set()
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            hashes = index.get("content_hashes")
            if index.get("version") != 1 or not isinstance(hashes, list) or not all(
                isinstance(key, str) for key in hashes
            ):
                raise ValueError("Invalid extraction completion index")
            completed.update(hashes)
        persisted = completed.copy()
        records = []
        # Read everything before compacting: corruption must never cause data loss.
        for path in sorted(self.path.glob("*.json")):
            if path == index_path:
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
            key = record["content_hash"]
            if record["status"] == "done":
                completed.add(key)
            elif record["status"] == "abandoned":
                if record.get("item", {}).get("content_hash", key) != key:
                    raise ValueError("Invalid extraction observation record")
                abandoned.add(key)
                records.append((path, record))
            elif record["status"] not in self._ACTIVE or record["item"]["content_hash"] != key:
                raise ValueError("Invalid extraction observation record")
            else:
                records.append((path, record))
        if completed != persisted:
            self._write_completed(completed)
        self._completed = completed
        self._abandoned = abandoned
        pending = []
        for path, record in records:
            if record["content_hash"] in completed:
                # The index is durable before redundant legacy/stale records go.
                path.unlink(missing_ok=True)
            else:
                pending.append(record)
        return pending + [{"content_hash": key, "status": "done"} for key in sorted(completed)]

    def write(
        self,
        item: dict[str, Any],
        status: str,
        *,
        error: str = "",
        attempts: int | None = None,
    ) -> None:
        if self._completed is None:
            self.load()
        assert self._abandoned is not None
        key = item["content_hash"]
        if key in self._completed or key in self._abandoned:
            return
        if status == "done":
            completed = self._completed | {key}
            self._write_completed(completed)
            self._completed = completed
            (self.path / f"{key}.json").unlink(missing_ok=True)
            return
        previous_attempts = 0
        target = self.path / f"{key}.json"
        if target.exists():
            try:
                previous = json.loads(target.read_text(encoding="utf-8"))
                previous_attempts = int(previous.get("attempts") or 0)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                previous_attempts = 0
        if attempts is None:
            attempts = previous_attempts + (1 if status in {"failed", "abandoned"} else 0)
        record = {
            "content_hash": key,
            "status": status,
            "item": item,
            "attempts": max(0, int(attempts)),
        }
        if error:
            record["error"] = error
        self._write_json(target, record)
        if status == "abandoned":
            self._abandoned.add(key)

    def _write_completed(self, completed: set[str]) -> None:
        self._write_json(self.path / "completed.json", {
            "version": 1, "content_hashes": sorted(completed),
        })

    def discard(self, item: dict[str, Any]) -> None:
        """空结果已结算，不进入恢复队列；后续显式阅读可以重新抽取。"""
        (self.path / f"{item['content_hash']}.json").unlink(missing_ok=True)

    def _write_json(self, target: Path, record: dict[str, Any]) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".observation-", dir=self.path)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            directory = os.open(self.path, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
