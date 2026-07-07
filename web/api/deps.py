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


def get_llm(model: str | None = None):
    from searchos.config.models import get_model_for

    return get_model_for(model or "judge")


def init_search_provider():
    # SearchOS binds search + page-fetch onto one shared browser provider.
    # Same resolution as the CLI: SF_SEARCH_PROVIDER, else infer from available
    # keys (serper → tavily), else the ragflow fallback.
    from searchos.tools.simple_browser.search import build_search_provider
    from searchos.tools.simple_browser.state import set_browser_provider

    set_browser_provider(build_search_provider())


WORKSPACE_ROOT = os.environ.get("SF_WORKSPACE_ROOT", str(_REPO_ROOT / "searchos_workspace"))

# In-memory session store: session_id → { task, result, status, ... }
sessions: dict[str, dict] = {}
