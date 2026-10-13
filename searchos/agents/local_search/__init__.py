"""Local Search agent — retrieves evidence from the authorized local library."""

from __future__ import annotations

AGENT_TYPE = "local_search_agent"


def get_tools(skill_names: list[str] | None = None, *, model_access: bool = False) -> list:
    """Local catalog/open/find only; never expose web or Access Skill tools."""
    from searchos.local.reader.tools import get_local_tools, local_catalog, local_find, local_open

    if model_access:
        return [local_catalog, local_open, local_find]
    return list(get_local_tools())


def create_qa_graph(model, *, middleware=()):
    """Use the shared SearchOS agent runtime for an authorized WebUI Local turn."""
    from pathlib import Path

    from langchain_core.tools import tool

    from searchos.agents.runtime import create_search_agent_graph
    from searchos.agents.toolset_render import render_toolset
    from searchos.config.settings import settings
    from searchos.harness.middleware.context import DynamicTrimMiddleware

    @tool("local_answer", return_direct=True)
    def local_answer(answer: str) -> str:
        """提交最终 Markdown 答案，包括原文引用；调用后结束本轮问答。"""
        if not answer.strip():
            raise ValueError("最终答案不能为空")
        return answer

    tools = [*get_tools(model_access=True), local_answer]
    persona = Path(__file__).with_name("agent.md").read_text(encoding="utf-8")
    persona = persona.partition("# Final summary")[0]
    persona = persona.replace("{toolset}", render_toolset(tools))
    return create_search_agent_graph(
        model=model, tools=tools,
        middleware=[
            DynamicTrimMiddleware(max_tokens_fraction=settings.dynamic_trim_fraction),
            *middleware,
        ], name=AGENT_TYPE,
        system_prompt=persona + "\n\n" + (
            "# Direct document QA\n"
            "本轮直接回答用户。资料范围是任务中列出的文档。"
            "优先使用本轮已提供的原文；尚未提供原文时，从任务中的 documents/*.md 目录开始，"
            "使用 local_find/local_open 阅读。已有原文足以回答时直接作答。"
            "根据问题和历史指代确定需要查找的信息，沿相关章节和后续页取得回答所需的依据。"
            "对完整清单、全文总结和跨文件比较，检查相应章节、后续范围和覆盖情况后再回答。"
            "事实使用实际 local_open 的原文支持；目录、local_find 提示和历史仅用于导航。"
            "回答直接给用户要的结果，重要事实附工具返回的 local:// 原文引用。"
            "重要事实就近标注工具提供的 [资料N]，系统会将其绑定为文件名和位置的可点击引用。"
            "也可使用工具返回的完整 local:// ref_id 写 Markdown 链接。"
            "可以分析和提出方案，但须区分资料事实、推断和建议；不要输出工具 ID 等执行细节。"
            "默认用紧凑篇幅解释核心结论、关键依据和必要局限，避免重复概述或逐节复述。"
            "用户要求详细分析、完整清单或逐项说明时，按要求充分展开。"
            "完成阅读后调用 local_answer 提交最终 Markdown 答案，该答案将实时显示给用户。"
            "答案应完整回应用户问题；来源不可用或运行预算耗尽时说明结果的实际范围。"
        ),
    )
