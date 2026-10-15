# Middleware 组件与默认组合

Middleware 以完整功能为单位装载。图入口接收实例列表；默认 pipeline 提供常用组合。组件内部封装投影、抽取输入转换和状态记录等实现步骤，调用方只传业务对象和必要参数。

## 网页装配

在「设置 → Middleware 装配」中选择调度、网页检索、本地检索、探索或写作用途，勾选组件并用上下箭头调整顺序，然后保存。列表默认只显示名称、开关和顺序；点击名称后展开说明、类名、生命周期钩子和挂载条件。支持按名称或类别筛选。编号表示 wrapper 从外到内的顺序；before / after 钩子仍按各自生命周期执行。

页面展示后续创建的 agent 的配置预览，已创建的 graph 保留原有实例。证据抽取依赖抽取模型，最终摘要还受任务的 `final_summary` 参数约束；实时追问依赖队列，上下文压缩依赖模型声明的上下文窗口。条件不满足的组件不会挂载。`graph.middleware` 仍是实际实例列表。

自定义组合保存到 `web_settings.json` 的 `middleware.pipelines`，Web 与 CLI/TUI 共享读取路径。未自定义的用途跟随原有设置，包括 SOCM 投影、工具历史压缩和网页检索过程折叠；自定义列表优先于这些默认开关。空列表表示不装载业务 middleware；「恢复默认」移除该用途的网页覆盖，重新采用环境配置与默认组合。手工传入 `middleware=[...]` 的代码入口不受网页组合影响。

`PUT /api/settings/middleware/{pipeline}` 接收 `{"selected": ["BudgetMiddleware", "DynamicTrimMiddleware"]}`；`selected: null` 恢复默认。接口拒绝未知组件、重复组件和不适用于该用途的组件，读取目录与组合使用 `GET /api/settings` 的 `middleware` 字段。

## 直接组合

```python
from searchos.agents.runtime import create_search_agent_graph
from searchos.harness.middleware import (
    BudgetMiddleware, BudgetState, ControlState, DynamicTrimMiddleware,
    ExtractionCoordinator, SOCMContextMiddleware, SourceContext,
    TaskContext, WebEvidenceMiddleware,
)

task_context = TaskContext(
    agent_id="reader", task_id="task-1", target_table="companies",
    task_text="查找目标公司的年收入",
)
source_context = SourceContext(workspace=workspace)
budget = BudgetState(max_queries=12, max_iterations=30)
control = ControlState()
extraction = ExtractionCoordinator(
    extraction_model, workspace=workspace, task=task_context,
)

graph = create_search_agent_graph(
    model=model,
    tools=tools,
    system_prompt=prompt,
    middleware=[
        BudgetMiddleware(budget, control=control),
        WebEvidenceMiddleware(extraction, source=source_context),
        SOCMContextMiddleware(workspace, task=task_context),
        DynamicTrimMiddleware(max_tokens=24000),
    ],
)
result = await graph.ainvoke(
    {"messages": [("user", task_context.task_text)]},
    {"configurable": {"thread_id": task_context.agent_id}},
)
```

`TaskContext` 保存任务身份和目标，`SourceContext` 保存来源 workspace 与访问范围。SOCM 未显式传入 control 时，图入口将它绑定到列表中唯一的共享 control；同一 agent 的运行层与组件必须共享同一个 control，多个不同实例会被拒绝。

列表表示模型与工具 wrapper 的外层到内层顺序。运行层在业务 wrapper 内侧执行控制信号和角色策略；预算在角色策略重试之外计量，一次逻辑轮次只计费一次。最终摘要使用 agent 结束钩子，不依赖它在 wrapper 列表中的位置。

每个 subagent 创建自己的 middleware 实例及可变状态；同一 agent 的继续执行复用这些状态。不要将一组有预算、去重和历史状态的组件复用于多个并发 subagent。

## 来源与抽取

```python
from searchos.harness.middleware import (
    FinalSummaryEvidenceMiddleware, LocalEvidenceMiddleware, WebEvidenceMiddleware,
)

middleware = [
    WebEvidenceMiddleware(extraction, source=source_context),
    LocalEvidenceMiddleware(extraction, source=local_source_context),
    FinalSummaryEvidenceMiddleware(extraction),
]
```

三类来源可以独立装载。Web 只处理网页及 Access Skill 页面，Local 只处理本地原文窗口，最终摘要只处理 agent 接受的最终 AI 回复。未装载摘要组件时不提交摘要；Hybrid 装载它后也可以提交 `agent://` 来源，核心不按 Hybrid 身份额外拒绝。

共享一个 extraction 时，Web 和 Local 复用抽取批次、提交记录及任务上下文。不同 extraction 可分别指定任务或抽取策略。

`ExtractionCoordinator(..., policy="task_rows")` 根据任务目标抽取并提交表格行；`policy="schema_facts"` 依据 schema 路由、保留原文窗口并提交事实。两者是显式抽取策略，不会读取 agent 角色来切换功能。核心的 store、routing、preparer 等注入接口用于内部扩展和测试，常规使用只需 model、workspace、task。

## 默认 pipeline

```python
from searchos.harness.middleware import web_search_pipeline

graph = web_search_pipeline(
    model=model,
    tools=tools,
    system_prompt=prompt,
    workspace=workspace,
    task=task_context,
    extraction_model=extraction_model,
    budget=BudgetState(max_queries=12),
    final_summary=False,
)
```

| 入口 | 默认用途 |
|---|---|
| `web_search_pipeline` | 网页检索、网页证据抽取及检索上下文管理 |
| `local_search_pipeline` | 本地检索、原文定位及本地证据抽取 |
| `explore_pipeline` | 探索轮次约束和上下文管理 |
| `writer_pipeline` | 写作状态投影与写作工具收尾 |
| `orchestrator_pipeline` | 调度预算、派发轮次、覆盖停滞和运行池提醒 |

Pipeline 返回可运行的 graph，和手写列表使用同一个 `create_search_agent_graph`。默认组合会读取已有 settings 决定装载哪些可选组件；组件本身不读取这些开关来隐式启用其他功能。Web/Local 接受显式的 `extraction_policy` 和 `final_summary`；调度入口根据任务需求选择参数。

需要完全自定义时直接传 `middleware=[...]`；调度入口 `_spawn_sub_agent(..., middleware=[...])` 同样接受完整替换，包括空列表。无需 factory 或 Assembly。`graph.middleware` 可查看本次显式装载的组件。

## 生命周期与可选功能

图入口仅管理已装载组件声明的资源。模型读状态前等待已触发的抽取批次；未满缓冲在结束时提交。正常结束、异常和取消都会收尾；共享资源每次运行只收尾一次，某个资源失败不会跳过其他资源。收尾失败会传播，已有运行异常保留为主异常并附上收尾错误。

`ainvoke` 返回前已经收尾。消费完整 `astream` 后也已收尾；主动提前停止消费时用 `contextlib.aclosing` 关闭流。调用方无需额外 barrier 或 extraction lifecycle。`middleware=[]` 不安装 SearchOS 业务机制；框架自己的基础运行设施仍由图入口管理。

预算、自动检测和历史压缩是可装配组件；停止执行、图片兼容和 session 日志由运行层管理。比如 `QueryRepetitionMiddleware(control, workspace=workspace, task=task_context)` 自己完成查询归一化、检测、警告和状态记录；不需要调用方再包装 detector 或编写记录回调。抽取组件不会自动安装这些功能。

[目录导航](../searchos/harness/middleware/README.md) · [用途与用法](../searchos/harness/middleware/USAGE.md)

## 运行职责边界

公开 middleware 保留 Context、Extraction、Sensor 三类，共 20 个组件。图片降级移入模型调用层，trajectory 与上下文注入日志移入 session telemetry，控制信号由 agent 运行层统一执行。Explore 轮次与调度空位提醒分别由 `ExplorePolicy`、`DispatchPolicy` 实现，通过 graph 的 `policy` 参数接入。

`create_search_agent_graph` 接收 `trajectory_logger`、`conversation_logger`、`workspace` 和 `agent_id`，即使 `middleware=[]` 也能记录运行。`image_fallback` 控制模型图片兼容；`control`、`drain_tools` 和 `finish_without_tools` 规定控制信号的执行方式。运行层不会在未装载对应 Sensor 时自行判断预算或停滞。

框架内部仍通过私有钩子适配模型和工具调用，但这些适配器不导出为业务组件，也不出现在 `graph.middleware` 中。完整参数示例见 [用途与用法](../searchos/harness/middleware/USAGE.md)。

新增 [CompactionContextMiddleware](../searchos/harness/middleware/context/COMPACTION_CONTEXT.md) 可在同一实例列表中装载。它通过 before-model 钩子持久化续接摘要，区别于只修改单次请求的上下文裁剪。
