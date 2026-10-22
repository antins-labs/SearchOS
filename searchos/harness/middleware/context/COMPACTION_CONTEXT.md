# CompactionContextMiddleware：上下文压缩调研与实现

调研日期：2026-09-29。实现入口为 [CompactionContextMiddleware](compaction_context_middleware.py)，消息边界与计量辅助函数位于 [utils/compaction.py](utils/compaction.py)。它属于 Context，只有显式装载才启用，不改动默认 pipeline。

## 公开资料确认了什么

Codex 配置暴露了自动压缩 token 阈值、上下文窗口和压缩提示词；当前还支持按全部活动上下文或压缩窗口前缀之后的增长量计算触发条件。阈值应随模型和任务配置，不能把某个固定数字当作所有 Codex 模型的规则。[官方配置说明](https://learn.chatgpt.com/docs/config-file/config-reference)

OpenAI 原生压缩返回一个供下一次请求使用的上下文窗口，其中可以包含不可读的加密压缩项以及保留下来的历史项。独立 `/responses/compact` 的结果应整体用于后续请求；送入压缩接口的输入也必须适合模型窗口。[官方压缩说明](https://developers.openai.com/api/docs/guides/compaction)

这些资料足以确认“阈值触发、建立新的活动上下文、从压缩结果继续”的机制，但不能证明普通文本摘要与服务端隐藏状态具有相同效果。本次未复刻 Codex 全部内部策略，也未声称采用其源码中的精确保留算法。

## SearchOS 的实现选择

当前 agent 通过跨厂商的 LangChain 消息接口运行。因此本组件实现文本续接摘要：在预算触发时，用调用方传入的摘要模型整理已完成的历史，将摘要与保留消息共同写入 graph state。它不使用 OpenAI 私有登录状态，不调用 `/responses/compact`，不模拟加密压缩项。

以下规则是 SearchOS 的具体设计，不是关于 Codex 内部实现的断言：

1. **提前触发。** 每次模型执行前估算活动消息 token，计入工具调用参数和消息开销，再加上系统提示、工具定义与动态上下文的预留额度。达到阈值才进行压缩。
2. **保留原始约束与当前状态。** 被压缩前缀中的真实用户消息、显式 SystemMessage 和最新 SOCM 投影原样保留。模型生成的摘要标为 synthetic，不伪装成新的用户请求。
3. **按完整交互保留近期历史。** 工具调用及其全部结果不能分开。最近交互超过保留额度时，将整个交互交给摘要；存在孤立结果或未完成调用时拒绝压缩。
4. **由模型选择保留信息。** 模型根据当前任务和未决请求，自主判断哪些历史值得保留、应如何表述。提示词提示它考虑目标与修正、已完成工作、决策、证据定位、失败尝试、未决问题和下一步，同时淘汰过时方案和重复细节，不强制逐项填写固定模板。每个分块同时提供将保留的用户指令和近期交互，让模型依据最新修正筛选旧历史。后续压缩将旧摘要与新增历史合并，避免累积多个摘要。
5. **摘要输入也受限。** 很长的历史分块滚动合并，每次请求预留摘要输出空间。非文本块仅记录省略类型，不把图片 Base64 送进文本摘要，也不编造图片内容。
6. **成功后一次替换。** 超长摘要允许基于同一原始输入重试一次，重试输入仍受相同预算限制。 全部摘要生成并检查长度后，才替换活动 messages。摘要错误、空输出、超长输出、超时和取消均不提交部分结果；异常交给调用方处理，不静默丢弃历史。
7. **恢复依赖 checkpoint。** 摘要消息和压缩计数保存在 thread state，不依赖 middleware 实例缓存。用同一 checkpointer 重建 graph 后仍可继续；不同 thread 的状态隔离。

## 初始化与运行

```python
from searchos.agents.runtime import create_search_agent_graph
from searchos.harness.middleware import CompactionContextMiddleware, SOCMContextMiddleware

graph = create_search_agent_graph(
    model=model,
    tools=tools,
    system_prompt=prompt,
    middleware=[
        SOCMContextMiddleware(workspace, task=task),
        CompactionContextMiddleware(
            summary_model,
            context_window=128_000,  # 可省略，默认读取模型 profile
            trigger_fraction=0.8,
            keep_recent_fraction=0.08,
            summary_fraction=0.02,
            reserve_fraction=0.08,
        ),
    ],
)
result = await graph.ainvoke(
    {"messages": [("user", "检索并对比目标公司的收入来源")]},
    {"configurable": {"thread_id": task.agent_id}},
)
# 首次成功压缩后可读取 count、before_tokens、after_tokens。
stats = result.get("context_compaction")
```

`summary_model` 使用现有模型配置创建的、未绑定工具的聊天模型，也可以复用 agent 的基础 model。`context_window` 指 agent 的窗口，省略时读取传入模型的 `profile.max_input_tokens`；无法读取时要求显式指定，不猜测默认窗口。摘要模型与 agent 不同时，应显式传入 agent 的窗口。摘要输入还会受摘要模型自身已知窗口的约束；未知时按显式窗口处理，需由调用方保证正确。模型调用会增加 token 消耗和延迟，不计入 BudgetMiddleware 的工具/逻辑轮次计数。

| 参数 | 语义 | 默认值 |
|---|---|---|
| `context_window` | agent 的上下文窗口，显式值优先 | 读取 model.profile.max_input_tokens |
| `trigger_fraction` | 自动压缩触发比例 | 0.8（80%） |
| `keep_recent_fraction` | 最近完整交互的保留比例 | 0.08（8%） |
| `summary_fraction` | 摘要输出的估算额度比例 | 0.02（2%） |
| `reserve_fraction` | 系统提示、工具定义和动态注入的预留比例 | 0.08（8%） |
| `token_counter` | 消息 token 计量函数，可替换为模型专用计量 | 内置估算 |
| `timeout` | 一次压缩所有分块的总超时，单位秒 | 120 |

例如窗口为 128000 token 时，默认触发阈值为 102400，近期历史额度为 10240，摘要额度为 2560，预留量为 10240。触发量是“活动消息估算 + 预留量”；因此消息本身不必达到窗口的 80%。

这些默认比例是本项目的选择。各比例须在 `[0, 1)` 内，触发与摘要比例须大于零；`reserve_fraction + keep_recent_fraction + summary_fraction` 必须小于触发比例。用户指令本身过长、没有可压缩历史或无法腾出足够空间时，组件明确报错；不会为了满足额度删除用户约束。保留比例与摘要比例是额度，并不保证压缩后总长度恰好为固定百分比，因为原始用户指令还需保留。

## 与其他组件的关系和边界

- DynamicTrim 仅裁剪单次模型输入；本组件会更新活动历史，checkpoint 中最新的 `messages` 不再是完整原始记录。完整执行轨迹仍应由 session logger 保存；历史 checkpoint 是否长期保留取决于 checkpointer。
- SOCM 按角色投影的内容变化更新 checkpoint 中的同一条消息；无变化时复用，空状态时删除。压缩保留该消息，后续请求和恢复继续读取最新状态。续接摘要只是历史辅助，不提交证据，也不取代 SOCM。
- 默认建议把本组件作为主要压缩策略，先不叠加 SearchEpisode 或 ToolHistory，避免多重压缩损失细节。需要末端裁剪时可另装 DynamicTrim，并为任务与摘要留足空间。
- 系统提示由 graph 每次提供，组件不改写它。压缩触发仍按活动历史与 reserve 判断；模型请求阶段另估算系统提示、工具定义和已注入消息，连同预留量超过窗口时明确报错。token 估算不是厂商计费值，需按使用模型调整。
- 请求 wrapper 顺序采用 SOCM 等注入 → 可选 DynamicTrim → Compaction 检查。Budget 必须在 Compaction 之前，先将工具消耗保存到 checkpoint；图入口会检查这一条件。运行层的角色提示可能在检查后追加，reserve 仍需留出余量。
- 图入口直接装配调用方选择的组件，不再隐式安装 DeepAgents 自动摘要；不装载本组件就不会执行本组件的压缩。
- 本版本按总量估算触发，没有实现 Codex 的 `body_after_prefix` 模式、服务端隐藏状态、跨会话记忆或上下文溢出后的模型重试。摘要质量依赖模型，结构和生命周期测试不等于语义无损保证。

验证入口：[test_compaction_context.py](../../../../tests/test_compaction_context.py)。测试覆盖阈值、工具配对、多次合并、长输入分块、失败原子性、取消、超时、真实 graph 恢复及 thread 隔离。
