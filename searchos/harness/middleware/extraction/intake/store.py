"""Evidence Intake 持久化 seam 及其 adapters。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from searchos.socm import SearchState


class EvidenceStore(Protocol):
    """Evidence Intake 所需的最小持久化 Interface。"""

    def load_state(self) -> SearchState: ...

    def atomic_update_state(self, updater: Callable[[SearchState], SearchState]) -> SearchState: ...

    def report_extraction_pending(self, owner: Any, count: int) -> None: ...


class WorkspaceEvidenceStore:
    """使用 WorkspaceManager 文件锁和 search_state.json 的生产 adapter。"""

    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace

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
