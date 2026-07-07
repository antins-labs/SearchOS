"""Skill Executor Runtime: run executor.py scripts in a controlled environment.

Provides a bridge between Sub Agents and executable access skills.
The executor gets access to browser tools (search, open, find)
but nothing else — no filesystem, no network beyond browser tools.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EXECUTOR_TIMEOUT = 60.0  # seconds — generous for proxied / overseas multi-request skills


async def run_executor(
    skill_path: Path,
    params: dict[str, Any],
    browser_tools: dict[str, Any],
    *,
    query: str = "",
    judge_model: Any = None,
) -> dict[str, Any]:
    """Execute a skill's executor.py with a ``SkillContext``.

    Args:
        skill_path: Path to the skill directory (containing executor.py)
        params: Arguments passed to ``execute()`` — the user-facing params
            declared in manifest.yaml's ``params_schema``.
        browser_tools: Dict of browser tool functions (search, open, find)
            exposed via ``ctx.browser`` for skills that fetch their own
            pages.
        query: Optional — the original user query, surfaced on
            ``ctx.query`` so skills can orient without re-deriving it.
        judge_model: Optional judge model for LLM-driven skills.

    Returns:
        The executor's return value, or ``{"error": "..."}`` on failure.
    """
    executor_path = skill_path / "executor.py"
    if not executor_path.exists():
        return {"error": f"No executor.py in {skill_path}"}

    # Executors hardcode their own network calls; route the ones that ignore
    # the env proxy (aiohttp / Playwright) through it. Idempotent no-op when
    # no proxy is configured.
    from searchos.skills.runtime.executor_proxy import install_executor_proxy_shims
    install_executor_proxy_shims()

    from searchos.skills.core.contract import SkillContext

    try:
        # Dynamic import of executor.py
        spec = importlib.util.spec_from_file_location("skill_executor", str(executor_path))
        if spec is None or spec.loader is None:
            return {"error": f"Cannot load executor: {executor_path}"}

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "execute"):
            return {"error": "executor.py has no execute() function"}

        ctx = SkillContext(
            query=query,
            skill_dir=skill_path,
            browser=_BrowserProxy(browser_tools),
            judge_model=judge_model,
        )

        # Run with timeout
        result = await asyncio.wait_for(
            module.execute(params, ctx),
            timeout=EXECUTOR_TIMEOUT,
        )

        logger.info("Executor %s completed: %s", skill_path.name, result.get("status", "unknown"))
        return result

    except asyncio.TimeoutError:
        logger.warning("Executor %s timed out after %.0fs", skill_path.name, EXECUTOR_TIMEOUT)
        return {"error": f"Executor timed out after {EXECUTOR_TIMEOUT}s"}
    except Exception as e:
        logger.warning("Executor %s failed: %s", skill_path.name, e)
        return {"error": str(e)}


class _BrowserProxy:
    """Proxy that exposes browser tools to executor scripts.

    Only search, open, and find are available.
    """

    def __init__(self, tools: dict[str, Any]) -> None:
        self._tools = tools

    @property
    def search(self) -> Any:
        return self._tools.get("search")

    @property
    def open(self) -> Any:
        return self._tools.get("open")

    @property
    def find(self) -> Any:
        return self._tools.get("find")
