"""Unified contract for access skills.

All access skills — whether URL-routed (invoked automatically by the
dispatcher after a page fetch) or agent-called (invoked via a typed tool
by a sub-agent) — share one runtime signature::

    async def execute(params: dict, ctx: SkillContext) -> dict

Which fields on ``ctx`` are populated depends on the invocation mode:

- **URL-routed**: dispatcher fills ``url`` / ``html`` / ``markdown`` /
  ``query`` / ``judge_model`` from the just-fetched page; ``browser`` is
  None (the skill should not fetch more pages — the dispatcher already
  did).
- **Agent-called**: sub-agent provides ``params`` from the tool call;
  ``browser`` exposes search/open/find for skills that do their own
  fetch. Page fields are empty.

``skill_dir`` is always set so skills can load sibling manifest files
(selectors.yaml, schema.py, prompt_hint.md).

Return shape convention:

- URL-routed skills MUST return ``{"facts": list[dict], ...}``. The
  dispatcher reads ``facts`` and feeds it into the evidence graph. One
  dict per extracted record.
- Agent-called skills return any dict shape; it's serialised and handed
  back to the sub-agent verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillContext:
    """Runtime context passed to every ``execute()`` call.

    Fields are grouped by invocation mode but are not enforced — a skill
    is free to use whatever is populated. The dispatcher and the
    agent-called tool registry each populate the relevant subset.
    """

    # ---- URL-routed mode (populated after dispatcher's page fetch) ----
    url: str = ""
    html: str = ""
    markdown: str = ""

    # ---- Always populated ----
    query: str = ""
    skill_dir: Path | None = None

    # ---- Agent-called mode (tools for skills that fetch on their own) ----
    browser: Any = None

    # ---- Shared resources ----
    judge_model: Any = None

    # Escape hatch for future additions without breaking existing skills.
    extras: dict[str, Any] = field(default_factory=dict)
