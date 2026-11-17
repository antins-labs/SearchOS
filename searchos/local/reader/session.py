"""绑定 Agent 的资料库、授权目录和已选文档快照。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from searchos.local.storage.sources import SourceRecord


@dataclass(slots=True)
class LocalBrowserState:
    """Per-agent local-library binding.

    Navigation itself is stateless: catalog paths and source references are
    explicit. The context variable only keeps concurrent agents on their own
    configured index root.
    """

    root: Path
    authorized_roots: tuple[Path, ...] | None = None
    selected_documents: dict[str, tuple[str, str]] | None = None
    selected_records: dict[str, SourceRecord] | None = None


_state_var: ContextVar[LocalBrowserState | None] = ContextVar(
    "searchos_local_browser",
    default=None,
)


def reset_local_browser(
    index_root: str | Path | None = None,
    *,
    source_roots: list[str | Path] | None = None,
    selected_documents: dict[str, tuple[str, str]] | None = None,
) -> LocalBrowserState:
    if index_root is None:
        from searchos.config.settings import settings

        index_root = settings.local_index_root
    authorized_roots = (
        tuple(Path(root).expanduser().resolve() for root in source_roots)
        if source_roots is not None
        else None
    )
    state = LocalBrowserState(
        root=Path(index_root).expanduser().resolve(),
        authorized_roots=authorized_roots,
        selected_documents=selected_documents,
    )
    _state_var.set(state)
    return state


def _state() -> LocalBrowserState:
    state = _state_var.get()
    if state is None:
        state = reset_local_browser()
    return state


@contextmanager
def selected_document_scope(index_root: str | Path, records: list[SourceRecord]):
    """Bind a document snapshot to this task and restore the caller's binding."""
    previous = _state_var.get()
    state = reset_local_browser(
        index_root, source_roots=[Path(record.source_path).parent for record in records],
        selected_documents={r.document_id: (r.source_revision, r.generation) for r in records},
    )
    state.selected_records = {r.document_id: r for r in records}
    try:
        yield state
    finally:
        _state_var.set(previous)
