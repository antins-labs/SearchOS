# Middleware 用途与用法

Middleware 在 agent 运行中执行一个可独立选择的功能。将实例放入 `middleware=[...]` 即可启用；每个 subagent 应创建自己的实例和可变状态。本文介绍根包导出的全部 20 种 middleware，内部基类和辅助函数不作为装配组件。

## 1. 从一个基本组合开始

下面假设已有 `model`、`extraction_model`、`tools`、`workspace` 和 `prompt`：分别是 agent 模型、抽取模型、工具列表、当前工作区和系统提示。工具由调用方提供，装载 middleware 不会自动添加检索工具。

```python
import searchos.harness.middleware as mw
from searchos.agents.runtime import create_search_agent_graph

task = mw.TaskContext(
    agent_id="reader_1",
    task_id="task_1",
    target_table="companies",
    task_text="查找目标公司的年收入",
)
source = mw.SourceContext(workspace=workspace)
budget = mw.BudgetState(max_queries=12, max_iterations=30)
control = mw.ControlState()
extraction = mw.ExtractionCoordinator(
    extraction_model, workspace=workspace, task=task,
)

graph = create_search_agent_graph(
    model=model,
    tools=tools,
    system_prompt=prompt,
    middleware=[
        mw.BudgetMiddleware(budget, control=control),
        mw.WebEvidenceMiddleware(extraction, source=source),
        mw.SOCMContextMiddleware(workspace, task=task),
        mw.DynamicTrimMiddleware(max_tokens=24000),
    ],
)
result = await graph.ainvoke(
    {"messages": [("user", task.task_text)]},
    {"configurable": {"thread_id": task.agent_id}},
)
```

后续片段沿用这些对象，只演示组件初始化，选定后放入图的 `middleware` 列表。额外变量会在对应小节说明。

| 共享对象 | 用途 |
|---|---|
| `TaskContext` | agent、任务、目标表和任务文本 |
| `SourceContext` | 来源 workspace 与本地文档访问范围 `scope` |
| `BudgetState` | 工具、轮次和时间预算及已使用量 |
| `ControlState` | 停止状态、工具限制和待注入的提醒 |
| `ExtractionCoordinator` | 接收观测、批量抽取、提交证据及记录进展 |

`ExtractionCoordinator` 默认使用 `policy="task_rows"`；需要依据 schema 路由并从原文窗口提交事实时，可显式传 `policy="schema_facts"`。这些共享对象本身不是 middleware。

## 2. Extraction：证据抽取

同一单元格中的不同表述不会直接触发 conflict。提交先过滤空容器和页面缺失说明，
再按完整投影、列定义和来源摘录批量判断兼容、矛盾或不确定。疑似矛盾必须提供双方
互斥的原文片段、确认共同口径，并通过交换两侧的独立复核，才设置 `has_conflict`。
模型调用发生在状态写锁外；提交时重新核对内容指纹，拒绝并发变更后的过期结果。

判定缓存位于 `coverage_map.evidence_comparisons`，包含列定义、来源范围、完整值、
摘录和规则版本的指纹。仅新证据对需要调用；兼容和不确定结果也缓存，调用异常在
60 秒后允许重试。每批至多 12 对、16,000 字符，单对超预算保留为不确定，不截断判断。
`conflict_status` 区分 `clear`、`pending`、`uncertain`、`confirmed`；`pending` 和
`uncertain` 不计为已确认冲突。`conflict_evidence_ids` 只保存当前冲突，
`conflict_history_evidence_ids` 保留历史记录。抽取和投影提交后增量核验，调度器每轮最多
补查 12 对，以覆盖手工写入及历史会话。网络复核不撤销已提交事实，不确定结果仍需保留来源限定。

### WebEvidenceMiddleware：网页证据

从 `open`、`find`、`read_visual` 等返回的网页窗口，以及符合页面格式的 Access Skill 结果中构造观测并提交抽取。保留原始 URL 和可见文本，跳过读取失败或不可抽取的页面。

```python
mw.WebEvidenceMiddleware(extraction, source=source)
```

它不会处理本地阅读结果，也不会从 agent 最终回答中抽取证据。

### LocalEvidenceMiddleware：本地原文证据

处理 `local_open` 返回的原文窗口，保留 `local://` 定位及文档元数据。传入访问范围后，检查并规范化文档引用；`local_find` 的检索命中不直接作为原文抽取输入。

```python
# source_scope 使用本地检索运行时已有的文档范围配置。
local_source = mw.SourceContext(workspace=workspace, scope=source_scope)
mw.LocalEvidenceMiddleware(extraction, source=local_source)
```

Web 与 Local 可以同时装载，并共用同一个 extraction。抽取合并保留互补字段及各自原文摘录；并发额度约束每次抽取模型调用。

使用 workspace 时，协调器将已接收但未结算的观测写入任务级日志；以相同任务和抽取策略重建后，在下一次模型调用前恢复处理。失败保留待处理项并返回明确回执；不自动无限重试。已提交结果的重放保持幂等。恢复仍会结算此前已接受的工作，即使重建时调整了来源 middleware；不接收未装载来源的新观测。同一任务同时只能有一个活跃协调器。内存 store 不提供跨进程恢复。

### FinalSummaryEvidenceMiddleware：最终回答证据

在 agent 结束时，从接受的最终 AI 回答中提交摘要观测，来源为 `agent://<agent_id>/final_summary`。跳过带工具调用的回复和过短内容；模型内部重试的候选回答不会被逐次提交。

```python
mw.FinalSummaryEvidenceMiddleware(extraction)
```

是否使用摘要来源只由装载决定，Hybrid 场景也可以装载。实际证据仍需通过抽取与提交校验。

## 3. Context：上下文与工具结果

### SOCMContextMiddleware：当前任务状态

在已触发的证据抽取提交后读取 workspace，生成当前角色的证据与缺口视图。没有相关表、任务或可用证据时不注入；路由预置计划不单独触发注入。模型调用成功后将最新投影保存为 checkpoint 中的一条固定 ID 消息，内容变化时原位更新，未变时直接复用，状态清空时删除。

完整对话日志保持追加语义：每次投影变化，都在当前轮的注入位置追加一条包含完整内容的 user 消息，位于此前工具回执之后、本轮模型回答之前。历史版本与各自的注入位置全部保留；checkpoint 只保存最新投影，不覆盖或删除这些日志记录。内容未变时不产生新的注入记录。

```python
mw.SOCMContextMiddleware(workspace, task=task)
```

`view` 可选 `"task"`、`"overview"`、`"writing"`，分别面向任务执行、调度和写作。未显式传 `control` 时，图入口绑定列表中唯一的共享控制状态；同一 agent 的组件和运行层必须共享同一个 control，传入多个不同实例会报错。

后续模型请求始终携带最新投影；DynamicTrim 和 Compaction 保留该消息。恢复执行图时按 workspace 校准 checkpoint 中的投影，没有 checkpoint 时也可从 workspace 重建。取消或失败的模型调用不提交投影更新。SOCM 只展示状态，操作方法来自角色提示词，停止约束由执行层处理。这里减少的是重复消息和更新事件，保留的状态仍会作为模型输入发送。

### CompactionContextMiddleware：持久化续接摘要

接近上下文阈值时，将较早的执行历史整理为任务续接摘要，并写入 checkpoint。保留真实用户指令、最新 SOCM 投影及预算内最近的完整工具交互；后续运行和断点恢复使用压缩后的活动历史。它是跨模型的文本版本，不等价于 OpenAI 服务端的加密压缩状态。

```python
# summary_model 是未绑定工具的聊天模型，可复用 agent 的基础 model。
mw.CompactionContextMiddleware(
    summary_model,
    context_window=128_000,  # 可省略，默认读取模型 profile
    trigger_fraction=0.8,
    keep_recent_fraction=0.08,
    summary_fraction=0.02,
    reserve_fraction=0.08,
)
```

`reserve_fraction` 为系统提示、工具定义和动态注入预留窗口比例，按实际任务调整。比例值使用 0–1，例如 `0.8` 表示 80%。只有全部摘要成功且腾出足够空间后才替换历史；摘要超长时基于原始输入限次重试一次；仍失败则抛出异常，原历史不变。模型调用前还会检查消息、系统提示、工具定义及预留空间；请将它放在上下文注入之后。默认 pipeline 不自动装载。调研依据、限制与恢复示例见 [Codex 上下文管理](context/COMPACTION_CONTEXT.md)。

### DynamicTrimMiddleware：按 token 预算裁剪

按消息正文、工具参数、系统提示和工具定义估算本次请求，超预算时裁剪旧历史。保留用户指令、纠正、最新状态和压缩交接摘要，工具事务整组保留或移除；必需上下文本身超限时明确报错。不会删除 checkpoint 中的原始历史；token 数为估算值。

```python
mw.DynamicTrimMiddleware(max_tokens=24000)
# 或按模型输入窗口比例设置；两个参数不能同时使用。
mw.DynamicTrimMiddleware(max_tokens_fraction=0.8)
```

### SearchEpisodeMiddleware：按检索轮次折叠历史

以名为 `search` 的工具调用划分检索轮次。已结束轮次折叠为工具输入、新增证据和覆盖变化，当前轮次保留详细消息；不调用模型生成摘要。

```python
mw.SearchEpisodeMiddleware(
    workspace, evidence_source=extraction, history_max_tokens=8000,
)
```

检索边界从当前历史重建，进展快照随消息写入 checkpoint；压缩或重建组件后不依赖旧消息下标。旧 checkpoint 缺少快照时只恢复工具历史，不推测过去的证据增量。适合使用 `search` 工具的网页检索流程。它与 DynamicTrim 的粒度不同：前者折叠已完成的检索轮次，后者控制模型输入长度。

### ToolHistoryMiddleware：压缩旧工具结果

在模型输入中保留最近若干条工具结果的完整文本，将较长的旧结果替换为简短标记。保留原始历史，不调用摘要模型。

```python
mw.ToolHistoryMiddleware(keep_recent=3, min_chars=200)
```

若任务需要反复对照本地原文，可以不装载该组件。

### ToolResultLimitMiddleware：限制单次工具结果长度

按工具名称截断返回的文本；映射中的数值是字符数，不是 token 数。未配置的工具和非文本结果保持原样。

```python
mw.ToolResultLimitMiddleware({"search": 6000, "explore_web": 48000})
```

它会改变写入对话的工具结果，区别于仅修改模型请求的 ToolHistory。与证据抽取同用时，将它放在抽取组件前，使返回结果先经过抽取，再被截断。

## 4. Sensor：预算、检测与进展

### RetryRouteMiddleware：避免重复失败路线

记录工具、页面或文档、阅读窗口、参数及结果，只对前次尝试中空结果或永久失败的相同调用执行拦截。同域其他页面、不同窗口和访问方法仍可用；旧 hostname 记录只作提示。适合重新分配过的 Frontier 任务；它不会自动重试模型或工具。

```python
mw.RetryRouteMiddleware(workspace, agent_id=task.agent_id)
```

### BudgetMiddleware：预算计量与限制

按底层实际动作计算工具消耗，对并发调用预留额度，并产生预算提示与耗尽信号。单项额度不足时拦截相应调用；整体耗尽时进入收尾状态。

运行层把动态预算、策略切换和停止信号追加为 user 消息，模型调用成功后按发送顺序保存到执行历史；相同内容保持原位，变化时追加新消息，不改写 system prompt。Explore 波次提示采用相同机制。日志在新消息实际发送的位置记录一次，回写历史不重复记录；工具额度与硬停止仍由执行层强制检查。

单项预算耗尽后，从下一轮模型的可选工具中移除对应工具，并提示剩余额度。
若出现 3 个有预算拒绝、且未执行其他计费动作的轮次，则以 `budget_rejection_loop`
强制收尾；同一轮并发拒绝只计一次。实际执行其他检索动作会清零计数，辅助工具不清零。
预算拒绝不产生抽取批次，因此由预算组件独立处理，拒绝记录和计数随 checkpoint 恢复。

```python
mw.BudgetMiddleware(
    budget, control=control, workspace=workspace, task=task,
)
```

`scope="run"`（默认）每次新调用重置预算；`scope="thread"` 在同一 thread 内累计已用额度和停止状态，并随 checkpoint 恢复：

```python
mw.BudgetMiddleware(budget, control=control, scope="thread")
```

恢复需沿用同一 checkpointer 和 thread_id；thread 时间预算包含暂停和停机期间的墙钟时间。一个 middleware 实例不得跨 thread 复用。工具完成回执随消息保存，用于恢复时补结算尚未写入预算快照的消耗。图入口自动绑定共享 control，由运行层执行停止与收尾。`workspace` 和 `task` 可省略；提供它们时会记录 agent 的预算耗尽状态。

### QueryRepetitionMiddleware：重复查询检测

在滑动窗口内归一化查询并检测重复，产生更换查询方式的提醒。提供 workspace 和 task 时，还会记录反模式；达到升级条件后标记 agent 为 `looped`。当前实现不会自行强制停止。

```python
mw.QueryRepetitionMiddleware(
    control, workspace=workspace, task=task,
    window=5, repetitions=3, escalation=2,
)
```

### ReadingReminderMiddleware：搜索后阅读提醒

连续搜索却未成功执行相应阅读或记录动作时，提醒模型打开原始来源。只产生提示，不负责证据抽取或强制停止。

```python
mw.ReadingReminderMiddleware(control, threshold=3)
```

### EmptyResultMiddleware：连续空结果提醒

连续出现结构化空结果或失败时，产生切换策略的信号；可以将相关反模式写入 workspace。优先读取工具状态与 artifact，旧工具回退到明确错误标记，不再用长度或正文是否包含 error 判断成功。它不判断事实是否成立。

```python
mw.EmptyResultMiddleware(
    control, workspace=workspace, task=task, threshold=5,
)
```

### StateStallMiddleware：任务状态停滞记录

检查覆盖分数、证据数量和待处理抽取数。多次工具调用后状态仍不变，且没有待处理抽取时，记录停滞并标记 agent 为 `looped`。当前实现不会自行强制停止。

```python
mw.StateStallMiddleware(workspace, control=control, task=task, threshold=6)
```

提供 task_id 时只观察当前任务关联的证据、绑定和单元格，避免其他 agent 的增长掩盖停滞；未提供任务时使用 workspace 全局状态。需要按当前 agent 的抽取批次判断时，使用 ProgressGuard。

### ProgressGuardMiddleware：按抽取批次判断无进展

读取 extraction 已结算批次的进展。连续若干批次没有新增证据、关联或填充进展时，发出停止信号。`limit` 的单位是已结算抽取批次，不是工具调用次数。

```python
mw.ProgressGuardMiddleware(extraction, control=control, task=task, limit=5)
```

与来源抽取组件一起装载；图入口会先等待已触发的抽取，再执行该检查。

### ToolProgressMiddleware：按工具调用判断无进展

比较工具执行前后的任务状态（无 task_id 时为 workspace 全局状态），连续调用仍没有证据或覆盖增长时发出停止信号。对于只找到链接、还未阅读来源的搜索结果，提供一次有限的阅读恢复机会。

```python
mw.ToolProgressMiddleware(control, workspace=workspace, task=task, limit=10)
```

适合未使用抽取服务的流程。有异步抽取时优先使用 ProgressGuard，避免在抽取尚未结算时判断无进展。

### ReadingProgressMiddleware：记录阅读活动

将识别到的网页或本地阅读活动写入共享集合，供调度者判断是否仍有阅读进展。集合中保存的是活动指纹，不是已验证证据，也不是来源 URL 清单。

```python
source_progress = set()
mw.ReadingProgressMiddleware(source_progress)
```

该集合可存入子 agent 的运行记录，交给 CoverageStall 汇总。

### DispatchRoundMiddleware：限制派发轮次

统计 `enqueue_tasks` 调用次数，达到上限后设置停止信号并限制继续派发。一批中包含多个任务仍按一次调用计数。

```python
mw.DispatchRoundMiddleware(control, max_rounds=5)
```

通常用于 orchestrator，在图入口通过 `drain_tools` 允许 `check_agents` 等收尾工具。

### CoverageStallMiddleware：判断多轮调度是否停滞

在 `check_agents` 返回一轮已完成的检索任务报告时，比较新增阅读、事实、任务关联、行和已填充单元格。连续若干完整轮次没有增长后，发出停止信号并限制新派发；仍有运行任务时不据此判定停滞。

```python
# agent_graphs 是调度运行时的 {agent_id: info} 映射，
# info["source_progress"] 可引用该子 agent 的阅读活动集合。
mw.CoverageStallMiddleware(
    workspace, control=control, agent_graphs=agent_graphs,
    max_stalled_rounds=3,
)
```

## 5. 组合顺序与默认 pipeline

列表中的 wrapper 按从外到内调用，结果按相反方向返回。SOCM、SearchEpisode、ToolHistory 等先处理上下文，DynamicTrim 或 Compaction 的请求检查放在它们之后；默认 pipeline 已按此装配。同时使用 DynamicTrim 和 Compaction 时，顺序为注入 → DynamicTrim → Compaction；持久化压缩仍在 before_model 阶段先执行，随后才裁剪和检查实际请求。Budget 必须放在 Compaction 前：其 before_model 先保存工具消耗，再允许压缩删除旧工具回执；图入口会检查这个顺序。角色 policy 在运行层仍可能追加少量提示，需保留窗口余量。下面展示“无进展停止 + 网页和本地抽取”的组合；沿用前文的 local_source。

```python
middleware = [
    mw.ProgressGuardMiddleware(extraction, control=control, task=task, limit=5),
    mw.BudgetMiddleware(budget, control=control),
    mw.ToolResultLimitMiddleware({"search": 6000}),
    mw.WebEvidenceMiddleware(extraction, source=source),
    mw.LocalEvidenceMiddleware(extraction, source=local_source),
    mw.SOCMContextMiddleware(workspace, task=task),
    mw.DynamicTrimMiddleware(max_tokens=24000),
]
```

图入口自动等待已触发的抽取，并在正常结束、异常和取消时收尾；共享 extraction 每次运行只收尾一次。无需额外装载 barrier 或手动包裹 extraction lifecycle。最终摘要是否启用，仍由是否添加 FinalSummaryEvidenceMiddleware 决定。

若只需要常用配置，可以调用默认 pipeline：

```python
graph = mw.web_search_pipeline(
    model=model,
    tools=tools,
    system_prompt=prompt,
    workspace=workspace,
    task=task,
    extraction_model=extraction_model,
    budget=mw.BudgetState(max_queries=12),
    final_summary=False,
)
```

其他入口为 `local_search_pipeline`、`explore_pipeline`、`writer_pipeline` 和 `orchestrator_pipeline`。默认组合读取现有 settings 决定装载哪些组件；需要精确控制行为时，直接使用实例列表。`graph.middleware` 可以查看显式装载的组件。

## 6. 运行设施与 agent 策略

图片兼容、session 日志和停止执行由 agent 运行层管理，不作为可装配的业务 middleware。Sensor 负责判断何时提醒或停止，运行层负责解释共享 control；未装载预算或停滞 Sensor 时，运行层不会自行产生对应条件。

```python
graph = create_search_agent_graph(
    model=model,
    tools=tools,
    system_prompt=prompt,
    middleware=[],
    control=control,
    workspace=workspace,
    trajectory_logger=trajectory_logger,
    conversation_logger=conversation_logger,
    agent_id=task.agent_id,
    emit_tool_started=True,
    image_fallback=True,
)
```

两个 logger 使用当前 session 的记录器；未传入时不记录对应日志。日志覆盖模型回复、工具输入输出及状态变化，运行层也记录实际注入模型的上下文。`emit_tool_started=True` 额外记录工具开始事件。

`image_fallback=True` 在模型明确拒绝图片输入时，将图片工具结果转换为识别文本并重试一次，需要已有图片识别配置。默认值 `None` 遵循当前运行配置，仅在图片阅读开启且模式为 `auto` 时启用。

调度或写作 agent 可在图入口设置 `drain_tools=frozenset({"check_agents"})` 和 `finish_without_tools=False`，保留收尾工具。若装载 Budget，也需为它配置一致的 `drain_tools`。这些参数只规定停止后的执行方式。

探索轮次和运行池提醒属于角色策略，由默认 pipeline 装配；手写组合也可通过图入口的 `policy` 参数指定：

```python
from searchos.agents.explore.policy import ExplorePolicy
from searchos.agents.orchestrator.policy import DispatchPolicy

# Explore agent：过早回答时提示继续探索，最多重试两次。
explore_policy = ExplorePolicy(min_waves=2, max_retries=2, control=control)

# Orchestrator：传入持续更新的 {agent_id: asyncio.Task} 映射。
dispatch_policy = DispatchPolicy(
    workspace, agents=task_pool, capacity=4,
    cooldown_s=10, max_reminders=3, control=control,
)
# 创建对应角色的 graph 时传 policy=explore_policy 或 policy=dispatch_policy。
```

这两个策略是普通对象。框架需要的模型与工具钩子由运行层内部接入，不要求调用方将日志、图片兼容或角色策略放入 `middleware` 列表。`middleware=[]` 表示不装载这三类业务机制，session 基础设施仍可正常工作。图入口直接使用 LangChain 的 ReAct 工厂，不隐式加载 DeepAgents 的自动摘要、文件卸载或默认工具；只有显式传入 skills/subagents 时才装配对应可选能力。

[目录导航](README.md) · [组合与生命周期说明](../../../docs/middleware-composition.md)
