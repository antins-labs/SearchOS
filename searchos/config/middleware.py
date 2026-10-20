"""Middleware 装配目录；网页预览与 pipeline 共用选择规则。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


def copy(zh: str, en: str) -> dict[str, str]:
    return {"zh": zh, "en": en}


PIPELINES = {
    "orchestrator": copy("调度", "Orchestrator"),
    "web_search": copy("网页检索", "Web search"),
    "local_search": copy("本地检索", "Local search"),
    "explore": copy("探索", "Explore"),
    "writer": copy("写作", "Writer"),
}
WORKER = (
    "BudgetMiddleware", "RetryRouteMiddleware", "QueryRepetitionMiddleware",
    "ReadingReminderMiddleware", "EmptyResultMiddleware",
    "SOCMContextMiddleware", "ToolHistoryMiddleware", "DynamicTrimMiddleware",
    "ToolResultLimitMiddleware",
)
PROGRESS = ("ProgressGuardMiddleware", "ToolProgressMiddleware", "ReadingProgressMiddleware", "StateStallMiddleware")
ORDERS = {
    "orchestrator": (
        "SteeringMiddleware", "BudgetMiddleware", "RetryRouteMiddleware",
        "DispatchRoundMiddleware", "CoverageStallMiddleware", "ToolResultLimitMiddleware",
        "SOCMContextMiddleware", "ToolHistoryMiddleware", "DynamicTrimMiddleware",
    ),
    "web_search": (*PROGRESS, "SearchEpisodeMiddleware", *WORKER, "WebEvidenceMiddleware", "FinalSummaryEvidenceMiddleware"),
    "local_search": (*PROGRESS, *WORKER, "LocalEvidenceMiddleware", "FinalSummaryEvidenceMiddleware"),
    "explore": WORKER,
    "writer": WORKER,
}


MOUNT_CONDITIONS = {
    "CompactionContextMiddleware": {"model_window": True},
    "SteeringMiddleware": {"steer_queue": True},
    "WebEvidenceMiddleware": {"extraction_model": True},
    "LocalEvidenceMiddleware": {"extraction_model": True},
    "FinalSummaryEvidenceMiddleware": {"extraction_model": True, "final_summary": True},
    "ProgressGuardMiddleware": {"extraction_model": True},
    "ToolProgressMiddleware": {"extraction_model": False},
    "StateStallMiddleware": {"workspace": True},
}


def entry(name, category, label, description, hooks, condition=None):
    return {
        "id": name, "category": category, "label": copy(*label),
        "description": copy(*description), "hooks": hooks,
        "condition": copy(*condition) if condition else None,
        "requirements": MOUNT_CONDITIONS.get(name, {}),
    }


CATALOG = [
    entry("SOCMContextMiddleware", "context", ("研究状态注入", "Research state injection"), ("将任务、证据与进度注入模型上下文。", "Project tasks, evidence and progress into model context."), ["wrap_model_call"]),
    entry("SearchEpisodeMiddleware", "context", ("检索历史折叠", "Search history folding"), ("折叠已完成的检索步骤，保留工具输入与进展。", "Fold completed search steps while keeping inputs and progress."), ["wrap_model_call"]),
    entry("ToolHistoryMiddleware", "context", ("旧工具结果压缩", "Older tool result compression"), ("压缩较早的工具输出。", "Compress older tool outputs."), ["wrap_model_call"]),
    entry("DynamicTrimMiddleware", "context", ("上下文裁剪", "Context trimming"), ("按 token 预算裁剪历史，保留任务锚点。", "Trim history to the token budget while preserving task anchors."), ["wrap_model_call"]),
    entry("CompactionContextMiddleware", "context", ("上下文压缩", "Context compaction"), ("将较早的对话整理为摘要并写回历史，供 agent 继续执行任务。", "Use the agent model to compact history and persist a handoff."), ["before_model", "wrap_model_call"], ("模型提供有效的上下文窗口时挂载；摘要会额外调用模型。", "Mounted when the model declares a valid context window; summarization adds model calls.")),
    entry("ToolResultLimitMiddleware", "context", ("工具结果限长", "Tool result limits"),
          ("根据可用上下文限制批量返回，其他工具保留各自限长。",
           "Bound batch output by available context; retain other tool limits."),
          ["wrap_model_call", "wrap_tool_call"]),
    entry("SteeringMiddleware", "context", ("实时追问", "Live follow-ups"), ("在模型边界接收用户追问与引导。", "Receive user follow-ups at model boundaries."), ["before_model", "wrap_model_call", "after_model"], ("提供追问队列时挂载。", "Mounted when a follow-up queue is provided.")),
    entry("WebEvidenceMiddleware", "extraction", ("网页证据抽取", "Web evidence"), ("从网页原文抽取并提交证据。", "Extract and commit evidence from web content."), ["wrap_tool_call"], ("提供抽取模型时挂载。", "Mounted when an extraction model is provided.")),
    entry("LocalEvidenceMiddleware", "extraction", ("本地证据抽取", "Local evidence"), ("从本地原文窗口抽取并提交证据。", "Extract and commit evidence from local source windows."), ["wrap_tool_call"], ("提供抽取模型时挂载。", "Mounted when an extraction model is provided.")),
    entry("FinalSummaryEvidenceMiddleware", "extraction", ("最终回复证据抽取", "Final answer evidence"), ("从 agent 的最终回复中提取证据。", "Extract evidence from the agent's final answer."), ["after_agent"], ("提供抽取模型且任务允许摘要抽取时挂载。", "Mounted with an extraction model when the task allows summary extraction.")),
    entry("BudgetMiddleware", "sensor", ("预算控制", "Budget control"), ("计量查询与迭代预算，触发收尾。", "Track query and iteration budgets and trigger wrap-up."), ["before_agent", "before_model", "after_model", "after_agent", "wrap_model_call", "wrap_tool_call"]),
    entry("RetryRouteMiddleware", "sensor", ("失败重试去重", "Failed retry deduplication"), ("记录访问结果，阻止后续重试重复已失败或无结果的查询与读取路径。", "Record access outcomes and block later retries of failed or empty routes."), ["wrap_tool_call"]),
    entry("QueryRepetitionMiddleware", "sensor", ("重复查询检测", "Repeated queries"), ("检测重复查询并记录停滞信号。", "Detect repeated queries and record stall signals."), ["wrap_tool_call"]),
    entry("ReadingReminderMiddleware", "sensor", ("阅读提醒", "Reading reminders"), ("连续搜索后提醒读取原文。", "Prompt source reading after repeated searches."), ["wrap_tool_call"]),
    entry("EmptyResultMiddleware", "sensor", ("空结果检测", "Empty results"), ("检测连续无结果的工具调用。", "Detect consecutive empty tool results."), ["wrap_tool_call"]),
    entry("ProgressGuardMiddleware", "sensor", ("证据进度检测", "Evidence progress"), ("根据抽取进展检测无效循环。", "Detect unproductive loops using extraction progress."), ["wrap_model_call"], ("提供抽取模型时挂载，与工具进度检测二选一。", "Mounted with an extraction model, instead of tool progress.")),
    entry("ToolProgressMiddleware", "sensor", ("工具进度检测", "Tool progress"), ("在没有抽取模型时，根据工具行为检测无效循环。", "Detect unproductive tool loops without an extraction model."), ["wrap_tool_call"], ("没有抽取模型时挂载，与证据进度检测二选一。", "Mounted without an extraction model, instead of evidence progress.")),
    entry("ReadingProgressMiddleware", "sensor", ("阅读进度记录", "Reading progress"), ("记录已读取的来源。", "Track sources that have been read."), ["wrap_tool_call"]),
    entry("StateStallMiddleware", "sensor", ("任务停滞检测", "Task stall detection"), ("根据任务状态判断连续无进展。", "Detect consecutive rounds without task progress."), ["wrap_tool_call"], ("提供 workspace 时挂载。", "Mounted when a workspace is provided.")),
    entry("DispatchRoundMiddleware", "sensor", ("调度轮数限制", "Dispatch round limit"), ("限制调度派发轮数。", "Limit dispatch rounds."), ["wrap_tool_call"]),
    entry("CoverageStallMiddleware", "sensor", ("调度停滞检测", "Orchestration stall detection"), ("根据证据、表格和阅读变化判断调度停滞。", "Detect orchestration stalls from evidence, table and reading progress."), ["wrap_tool_call"]),
]


def available(pipeline: str) -> list[str]:
    return [*ORDERS[pipeline], "CompactionContextMiddleware"]


def validate_pipelines(value: dict[str, list[str]]) -> dict[str, list[str]]:
    for pipeline, names in value.items():
        if pipeline not in PIPELINES:
            raise ValueError(f"Unknown pipeline: {pipeline}")
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate middleware in {pipeline}")
        unknown = set(names) - set(available(pipeline))
        if unknown:
            raise ValueError(f"Unsupported middleware in {pipeline}: {sorted(unknown)}")
        if ("BudgetMiddleware" in names and "CompactionContextMiddleware" in names
                and names.index("BudgetMiddleware") > names.index("CompactionContextMiddleware")):
            raise ValueError("Place BudgetMiddleware before CompactionContextMiddleware")
    return value


class MiddlewareOverlay(BaseModel, extra="forbid"):
    pipelines: dict[str, list[str]] = Field(default_factory=dict)

    _validate = field_validator("pipelines")(validate_pipelines)


def default_selection(pipeline: str, settings) -> list[str]:
    excluded = set()
    if not settings.enable_socm_projection:
        excluded.add("SOCMContextMiddleware")
    if not settings.compress_old_tool_results or pipeline == "local_search":
        excluded.add("ToolHistoryMiddleware")
    if not settings.use_layered_context:
        excluded.add("SearchEpisodeMiddleware")
    return [name for name in ORDERS[pipeline] if name not in excluded]


def selection(pipeline: str, settings) -> list[str]:
    configured = settings.middleware_pipelines.get(pipeline)
    return list(configured) if configured is not None else default_selection(pipeline, settings)


def middleware_view(settings) -> dict:
    return {
        "catalog": CATALOG,
        "pipelines": [
            {"id": key, "label": label, "available": available(key),
             "selected": selection(key, settings), "defaults": default_selection(key, settings),
             "customized": key in settings.middleware_pipelines}
            for key, label in PIPELINES.items()
        ],
    }
