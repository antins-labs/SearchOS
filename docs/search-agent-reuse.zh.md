# Search Agent 续派

为避免相关任务重复发现和加载技能，Orchestrator 可以在 `enqueue_tasks` 的任务对象中指定 `agent_id`，继续使用已有检索 Agent。省略该字段时，仍创建新 Agent。

派发时优先选择已有工具和来源上下文适用的空闲 Agent。Orchestrator 根据最近一次 `check_agents` 返回的 `reusable_agents`，结合已加载技能、上一任务和来源判断；没有合适的空闲 Agent、需要全新上下文或需要并行执行独立工作时，再创建新 Agent。适用的已加载技能直接复用，来源或能力要求变化时再发现和加载。

## 调用

先用 `check_agents` 收取报告。返回的 `reusable_agents` 包含空闲且兼容的 Agent ID、角色、上一任务和已加载技能名。选择与后续目标相关的 Agent，提交新的任务：

下面是一个任务对象，将其放入 `enqueue_tasks` 的任务数组，外层编码遵循当前工具 schema：

```json
{
  "agent_type": "search_agent",
  "agent_id": "search_agent",
  "task": "继续使用已读取的官方资料，核对尚未确认的版本差异，并保留来源。",
  "result_mode": "findings"
}
```

示例 ID 需替换为 `reusable_agents` 中实际返回的值。`id` 仍是新 Frontier Task 的 ID，不能用它指定 Agent。原有 `target_table`、`target_cells`、`max_searches`、`priority` 和 `blocked_by` 均保持任务级语义。

## 状态与边界

- 支持 `search_agent` 和 `local_search_agent`；角色、资料快照和访问策略必须与原 Agent 兼容。
- 保留同一 Agent ID、thread、对话历史与浏览器状态，包括原有页面引用和本地阅读上下文。
- 继承已加载技能包的固定版本，适用时直接执行；来源或能力要求改变时再发现和加载。每次执行仍检查技能可用性和访问策略。
- 每次派发建立独立 TaskContext、抽取队列、进度检测和执行预算，历史证据不会因复用自动改绑。会话总预算和并发上限继续生效，续派不消耗新 Agent 创建额度。
- 技能工作目录和调用回执按任务隔离，避免新任务重放旧执行结果。需要旧原文支持新结论时，应重新读取或按已有证据复用规则处理。
- 每次任务单独提交报告；尚未交付的旧报告会随 `check_agents` 一并返回。

正在执行的 Agent 不接受新的指定派发。同一批中给空闲 Agent 排入多个任务时，调度器逐个执行。取消后仍在收尾的 Agent 继续占用容量；存在未完成 checkpoint 的 Agent 不接受续派。

复用仅限当前进程中同一次 Orchestrator 运行。服务重启或新运行不会恢复内存中的 Agent registry。使用自定义 middleware、额外工具或直接 steering 的专用 Agent 不在此续派范围内。指定的 Agent 不可用时返回原因，不静默创建替代 Agent。
