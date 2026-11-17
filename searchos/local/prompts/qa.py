"""本地问答的任务输入和运行提示。"""

DIRECT_QA = """# Direct document QA
直接回答用户的问题，遵循任务给出的资料范围。优先使用本轮已读取的原文，按需继续读取相关章节和后续窗口。
完整清单、全文总结和跨文件比较需检查覆盖范围。
事实依据来自已读原文，目录和历史用于导航。
重要事实就近标注工具提供的 [资料N]，或使用完整 local:// 引用。区分资料事实、推断和建议。
按用户要求控制详略，说明影响结论的来源限制。调用 local_answer 提交最终 Markdown 答案。"""

BUDGET_EXHAUSTED = "工具预算已用完。请根据已读原文调用 local_answer 作答，说明未覆盖的范围。"
READ_REQUIRED = "请先用 local_open 读取相关原文，再回答问题。"
PRELOAD_COMPLETE = "所选文档的解析正文已读取。请回答问题，按需核对图表或细节。"
PRELOAD_PARTIAL = "预读尚未覆盖全部正文。请检查工具结果，按需继续读取。"
HISTORY_OMITTED = "\n[历史节选]\n"
SOURCE_LABEL = "[资料{number}] {path} · {location}\n{content}"
ANSWER_TOOL = "提交最终 Markdown 答案并结束本轮问答。answer 为非空正文，重要事实附已读来源引用。"


def build_task(query: str, scope: str, history: str, tool_calls: int) -> str:
    return f"""问题：{query}

{scope}

对话历史（用于理解指代）：
{history}

本轮工具调用上限：{tool_calls}。阅读必要原文后回答问题。"""


def build_scope(documents: str | None) -> str:
    if documents is None:
        return "资料范围：当前知识库。先用 local_catalog(query=...) 查找相关目录，再读取原文。"
    return f"资料范围：以下文档。\n{documents}"
