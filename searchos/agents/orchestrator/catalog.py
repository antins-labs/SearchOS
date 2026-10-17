"""Agent Catalog: directory of available Sub Agents for the Orchestrator.

The Main Agent sees this catalog and decides which Sub Agent(s) to dispatch.
Each entry's ``tools`` field is **derived** from the same per-role
``get_tools()`` the spawn path uses — so renaming or adding a tool propagates
here without manual double-maintenance. Skills stay decoupled: the Main Agent
reads the full skill catalog from the SkillRegistry and decides what to inject.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from searchos.agents import explore, local_search, search, writer


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


# Explore 在首次检索或后续检索中按具体的不确定性派发。
AGENT_CATALOG: list[AgentSpec] = [
    AgentSpec(
        name=explore.AGENT_TYPE,
        description=(
            "Resolve uncertainty about identity, scope, candidate sets, or source strategy "
            "before or during search. Follow the Orchestrator's initial-action policy."
        ),
        tools=_tool_names(explore.get_tools()),
    ),
    AgentSpec(
        name=search.AGENT_TYPE,
        description="Search the web for evidence. No local-document tools.",
        tools=_tool_names(search.get_tools()),
    ),
    AgentSpec(
        name=local_search.AGENT_TYPE,
        description=(
            "Search the authorized local document library for evidence. "
            "No web tools or Access Skills."
        ),
        # Local tools are resolved again at render time because their
        # enablement can change after this module is imported.
        tools=[],
    ),
    AgentSpec(
        name=writer.AGENT_TYPE,
        description="Long-lived structured drafter for the final report generation.",
        tools=_tool_names(writer.get_tools()),
    ),
]


def _is_agent_enabled(name: str) -> bool:
    """Per-agent enablement gate.

    Filter at the source so the orchestrator never sees a disabled agent and
    never tries to dispatch it directly.
    """
    from searchos.config.settings import settings
    from searchos.tools.search_state import _source_scope_var

    if name == explore.AGENT_TYPE and not settings.enable_explore:
        return False
    scope = _source_scope_var.get()
    if scope is not None:
        if name == local_search.AGENT_TYPE:
            return scope.get("mode") in {"local", "hybrid"} and bool(scope.get("documents"))
        if name in {search.AGENT_TYPE, explore.AGENT_TYPE}:
            if scope.get("mode") == "local" or "web" in scope.get("unavailable_sources", {}):
                return False

    if name == writer.AGENT_TYPE:
        return bool(settings.enable_writer_agent)
    if name == local_search.AGENT_TYPE:
        # Global tool configuration does not grant a run access to a library.
        # Runs without an explicit source scope retain the Web entry contract.
        return False
    return True


def _rendered_tools(spec: AgentSpec) -> list[str]:
    """Resolve settings-dependent toolsets at prompt construction time."""
    if spec.name == local_search.AGENT_TYPE:
        from searchos.tools.search_state import _source_scope_var

        return _tool_names(local_search.get_tools(model_access=_source_scope_var.get() is not None))
    return spec.tools


def generate_agent_catalog_text() -> str:
    """Generate the catalog text injected into the Main Agent's system prompt.

    Disabled agents (per ``_is_agent_enabled``) are hidden so the orchestrator
    never tries to dispatch them.
    """
    visible = [s for s in AGENT_CATALOG if _is_agent_enabled(s.name)]
    lines = [f"[Available Sub Agents — {len(visible)} pre-built]"]
    for spec in visible:
        tools = _rendered_tools(spec)
        tools_str = ", ".join(tools[:6])
        if len(tools) > 6:
            tools_str += f", … ({len(tools)} total)"
        lines.append(f"- **{spec.name}**: {spec.description}")
        lines.append(f"  Tools: {tools_str}")
    return "\n".join(lines)
