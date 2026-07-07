"""Render a LangChain tool list as a markdown section for system prompts.

Used by ``_spawn_sub_agent`` to fill the ``{toolset}`` placeholder in each
agent.md and by ``build_orchestrator_prompt`` to fill ``{orch_toolset}``.
Keeps agent personas decoupled from tool signatures — add/remove a tool
and the prompt stays in sync automatically.
"""

from __future__ import annotations

from typing import Any


def _first_paragraph(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    for i, line in enumerate(text.splitlines()):
        if i > 0 and not line.strip():
            return "\n".join(text.splitlines()[:i]).strip()
    return text


def _render_args(tool: Any) -> str:
    schema = getattr(tool, "args_schema", None)
    fields = getattr(schema, "model_fields", None) if schema is not None else None
    if not fields:
        return ""
    parts: list[str] = []
    for fname, finfo in fields.items():
        ann = getattr(finfo, "annotation", None)
        tname = getattr(ann, "__name__", None) or (str(ann) if ann is not None else "Any")
        is_required = getattr(finfo, "is_required", None)
        required = is_required() if callable(is_required) else True
        parts.append(f"{fname}: {tname}" + ("" if required else "?"))
    return ", ".join(parts)


def render_toolset(tools: list, *, header: str = "## Available Tools") -> str:
    """Render ``tools`` as markdown. Returns empty string if ``tools`` is empty.

    Each tool becomes:
      ### name(args)
      first-paragraph description
    """
    if not tools:
        return ""
    lines: list[str] = [header, ""]
    for t in tools:
        name = getattr(t, "name", None) or getattr(t, "__name__", "<anonymous>")
        desc = _first_paragraph(getattr(t, "description", "") or "")
        args = _render_args(t)
        lines.append(f"### {name}({args})")
        if desc:
            lines.append(desc)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
