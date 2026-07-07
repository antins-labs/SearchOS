"""Agent Catalog: directory of available Sub Agents for the Orchestrator.

The Main Agent sees this catalog and decides which Sub Agent(s) to dispatch.
Each entry's ``tools`` field is **derived** from the same per-role
``get_tools()`` the spawn path uses — so renaming or adding a tool propagates
here without manual double-maintenance. Skills stay decoupled: the Main Agent
reads the full skill catalog from the SkillRegistry and decides what to inject.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from searchos.agents import explore, search, writer


@dataclass
class AgentSpec:
    """Specification for a pre-built Sub Agent."""

    name: str
    description: str
    tools: list[str] = field(default_factory=list)


def _tool_names(tools: list) -> list[str]:
    """Extract ``tool.name`` from a list of LangChain ``@tool`` callables."""
    out: list[str] = []
    for t in tools:
        name = getattr(t, "name", None) or getattr(t, "__name__", None)
        if name:
            out.append(str(name))
    return out


# Pre-built agent catalog. explore_agent is included: the orchestrator
# dispatches it when the query is too vague to create a schema from directly.
AGENT_CATALOG: list[AgentSpec] = [
    AgentSpec(
        name=explore.AGENT_TYPE,
        description=(
            "Explore the distribution of information, which is applicable "
            "to complex and open-ended information seeking tasks."
        ),
        tools=_tool_names(explore.get_tools()),
    ),
    AgentSpec(
        name=search.AGENT_TYPE,
        description="Solve a search task given by the orchestrator.",
        tools=_tool_names(search.get_tools()),
    ),
    AgentSpec(
        name=writer.AGENT_TYPE,
        description="Long-lived structured drafter for the final report generation.",
        tools=_tool_names(writer.get_tools()),
    ),
]


def get_agent_spec(name: str) -> AgentSpec | None:
    """Look up an agent spec by name."""
    for spec in AGENT_CATALOG:
        if spec.name == name:
            return spec
    return None


def _is_agent_enabled(name: str) -> bool:
    """Per-agent enablement gate.

    Only ``writer_agent`` has an opt-in setting (``enable_writer_agent``).
    Filter at the source so the orchestrator never sees a disabled agent and
    never tries to dispatch it directly.
    """
    if name == writer.AGENT_TYPE:
        from searchos.config.settings import settings
        return bool(settings.enable_writer_agent)
    return True


def generate_agent_catalog_text() -> str:
    """Generate the catalog text injected into the Main Agent's system prompt.

    Disabled agents (per ``_is_agent_enabled``) are hidden so the orchestrator
    never tries to dispatch them.
    """
    visible = [s for s in AGENT_CATALOG if _is_agent_enabled(s.name)]
    lines = [f"[Available Sub Agents — {len(visible)} pre-built]"]
    for spec in visible:
        tools_str = ", ".join(spec.tools[:6])
        if len(spec.tools) > 6:
            tools_str += f", … ({len(spec.tools)} total)"
        lines.append(f"- **{spec.name}**: {spec.description}")
        lines.append(f"  Tools: {tools_str}")
    return "\n".join(lines)
