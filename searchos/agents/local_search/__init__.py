"""Local Search agent — retrieves evidence from the authorized local library."""

from __future__ import annotations

from searchos.local import messages

AGENT_TYPE = "local_search_agent"


def get_tools(skill_names: list[str] | None = None, *, model_access: bool = False) -> list:
    """Local catalog/open/find only; never expose web or Access Skill tools."""
    from searchos.local.reader import get_local_tools, local_catalog, local_find, local_open

    if model_access:
        return [local_catalog, local_open, local_find]
    return list(get_local_tools())


def create_qa_graph(model, *, middleware=()):
    """Use the shared SearchOS agent runtime for an authorized WebUI Local turn."""
    from pathlib import Path

    from langchain_core.tools import tool

    from searchos.agents.local_search.qa import ANSWER_TOOL, DIRECT_QA
    from searchos.agents.runtime import create_search_agent_graph
    from searchos.agents.toolset_render import render_toolset
    from searchos.config.settings import settings
    from searchos.harness.middleware.context import DynamicTrimMiddleware

    @tool("local_answer", return_direct=True, description=ANSWER_TOOL)
    def local_answer(answer: str) -> str:
        """提交本轮问答结果。"""
        if not answer.strip():
            raise ValueError(messages.ANSWER_EMPTY)
        return answer

    tools = [*get_tools(model_access=True), local_answer]
    persona = Path(__file__).with_name("agent.md").read_text(encoding="utf-8")
    persona = persona.partition("# Final summary")[0]
    persona = persona.replace("{toolset}", render_toolset(tools))
    return create_search_agent_graph(
        model=model,
        tools=tools,
        middleware=[
            DynamicTrimMiddleware(max_tokens_fraction=settings.dynamic_trim_fraction),
            *middleware,
        ],
        name=AGENT_TYPE,
        system_prompt=f"{persona}\n\n{DIRECT_QA}",
    )
