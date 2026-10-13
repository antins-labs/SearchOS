"""Evidence Extraction 持久化 seam 及其 adapters。"""

from __future__ import annotations

from collections.abc import Callable
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


class InMemoryEvidenceStore:
    """无需 Agent Middleware 或文件系统的测试 adapter。"""

    def __init__(self, state: SearchState | None = None) -> None:
        self.state = state or SearchState()
        self.pending_by_owner: dict[int, int] = {}

    def load_state(self) -> SearchState:
        return self.state.model_copy(deep=True)

    def atomic_update_state(self, updater: Callable[[SearchState], SearchState]) -> SearchState:
        self.state = updater(self.state.model_copy(deep=True))
        return self.state.model_copy(deep=True)

    def report_extraction_pending(self, owner: Any, count: int) -> None:
        self.pending_by_owner[id(owner)] = max(0, int(count))


class _ObservationJournal:
    """任务内的抽取日志；原子发布单条记录，不混入已提交 SourceObservation。

    调度方须保证同一任务仅有一个活跃协调器。不同任务与抽取策略隔离；
    重建协调器可恢复 pending/failed，done 只保存幂等标记。
    """

    def __init__(self, root: Any, owner: str) -> None:
        import hashlib
        from pathlib import Path

        self.path = Path(root) / "extraction_pending" / hashlib.sha256(owner.encode()).hexdigest()
        self.path.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict[str, Any]]:
        import json

        # JSON corruption is a real recovery failure; never silently drop it.
        return [json.loads(path.read_text()) for path in sorted(self.path.glob("*.json"))]

    def write(self, item: dict[str, Any], status: str, *, error: str = "") -> None:
        import json
        import os
        import tempfile

        key = item["content_hash"]
        record = {"content_hash": key, "status": status}
        if status != "done":
            record["item"] = item
            if error:
                record["error"] = error
        descriptor, temporary = tempfile.mkstemp(prefix=".observation-", dir=self.path)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path / f"{key}.json")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
