"""Dependency injection — LLM, SearchProvider, shared state."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# …/SearchOS  (web/api/deps.py → parent×3)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Load .env from repo root
_env_path = _REPO_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


def init_search_provider(name: str | None = None):
    # SearchOS binds search + page-fetch onto one shared browser provider.
    # An explicit ``name`` (from web settings) wins; otherwise same resolution
    # as the CLI: SF_SEARCH_PROVIDER, else infer from available keys
    # (serper → tavily), else the ragflow fallback.
    from searchos.tools.simple_browser.search import build_search_provider
    from searchos.tools.simple_browser.state import set_browser_provider

    set_browser_provider(build_search_provider(name or ""))


WORKSPACE_ROOT = os.environ.get("SF_WORKSPACE_ROOT", str(_REPO_ROOT / "searchos_workspace"))


LOCAL_DATA_ROOT = os.environ.get("SF_LOCAL_DATA_ROOT") or str(_REPO_ROOT / "knowledge_base")

# Web settings overlay — next to .env, NOT inside WORKSPACE_ROOT (whose
# subdirectories are scanned as sessions by history.py).
WEB_SETTINGS_PATH = os.environ.get("SF_WEB_SETTINGS_PATH", str(_REPO_ROOT / "web_settings.json"))

# The .env file web-set keys/provider knobs are persisted to. SF_ENV_FILE
# exists so tests can point writes at a tmp path.
ENV_FILE_PATH = os.environ.get("SF_ENV_FILE", str(_REPO_ROOT / ".env"))

# In-memory session store: session_id → { task, result, status, ... }
sessions: dict[str, dict] = {}


def session_directory(root: str | Path, session_id: str) -> Path:
    """API 的统一 session 路径解析，保留旧链接并拒绝越界路径。"""
    from fastapi import HTTPException
    from searchos.socm.storage.workspace import resolve_session_path

    try:
        return resolve_session_path(root, session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
