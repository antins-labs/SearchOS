"""Workspace routes — file browsing and content retrieval."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from api.deps import WORKSPACE_ROOT

router = APIRouter(prefix="/api/workspace")


@router.get("/{session_id}/files")
async def list_workspace_files(session_id: str):
    """Return workspace file tree."""
    ws_path = Path(WORKSPACE_ROOT) / session_id
    if not ws_path.exists():
        raise HTTPException(404, f"Workspace {session_id} not found")

    tree = _build_tree(ws_path, ws_path)
    return {"session_id": session_id, "tree": tree}


@router.get("/{session_id}/file")
async def get_file_content(session_id: str, path: str = Query(...)):
    """Read a single file from workspace."""
    ws_path = Path(WORKSPACE_ROOT) / session_id
    file_path = (ws_path / path).resolve()

    # Prevent path traversal
    if not str(file_path).startswith(str(ws_path.resolve())):
        raise HTTPException(403, "Path traversal not allowed")

    if not file_path.exists():
        raise HTTPException(404, f"File not found: {path}")

    if not file_path.is_file():
        raise HTTPException(400, f"Not a file: {path}")

    # Limit file size
    if file_path.stat().st_size > 1_000_000:
        return {"path": path, "content": "(file too large, > 1MB)", "truncated": True}

    content = file_path.read_text(encoding="utf-8", errors="replace")
    return {"path": path, "content": content, "size": len(content)}


def _build_tree(root: Path, current: Path) -> list[dict]:
    """Recursively build file tree. Pages directory uses index.json for readable names."""
    import json as _json

    # Check if this is the pages/ directory and has an index
    page_index: dict = {}
    if current.name == "pages":
        idx_path = current / "index.json"
        if idx_path.exists():
            try:
                page_index = _json.loads(idx_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    items = []
    for entry in sorted(current.iterdir()):
        if entry.name == "index.json" and page_index:
            continue  # Don't show index.json itself in pages/
        rel = str(entry.relative_to(root))
        if entry.is_dir():
            children = _build_tree(root, entry)
            if children:
                items.append({
                    "name": entry.name,
                    "type": "directory",
                    "path": rel,
                    "children": children,
                })
        else:
            name = entry.name
            # Use page index for readable display names
            if page_index and entry.suffix == ".md":
                page_id = entry.stem
                meta = page_index.get(page_id)
                if meta:
                    name = meta.get("title") or meta.get("domain", "") + meta.get("path", "")
                    name = name[:60]  # cap length
            items.append({
                "name": name,
                "type": "file",
                "path": rel,
                "size": entry.stat().st_size,
            })
    return items
