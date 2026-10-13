"""Runtime contract for access-skill executors.

Access skills are invoked as typed tools by sub-agents and share one runtime
signature::

    async def execute(params: dict, ctx: SkillContext) -> dict

The sub-agent provides ``params`` from the tool call. The executor runs in an
isolated process. Skills fetch through direct HTTP or self-managed Playwright
Browser Automation.

``skill_dir`` is always set so skills can load sibling manifest files
(for example static lookup data).

Executors return a dict, which is serialised and handed back to the sub-agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SkillContext:
    """Runtime context passed to every isolated ``execute()`` call."""

    query: str = ""
    skill_dir: Path | None = None
