# Search Agent 续派

为避免相关任务重复发现和加载技能，Orchestrator 可以在 `enqueue_tasks` 的任务对象中指定 `agent_id`，继续使用已有检索 Agent。省略该字段时，仍创建新 Agent。

派发时优先选择已有工具和来源上下文适用的空闲 Agent。Orchestrator 从最新报告的 `reusable_agents` 读取候选，结合已加载技能、上一任务和来源判断；需要并行检索或没有合适的上下文时，再创建新 Agent。

## 调用

`enqueue_tasks` 派发后直接返回回执，Orchestrator 可以继续补表或核对已有证据。子任务报告按完成顺序排队，每轮模型调用接收一份，其余子任务继续运行。空闲时调用 `check_agents` 等待下一份报告，传入 `timeout` 可指定最长等待秒数。`reusable_agents` 列出可续派的 Agent、角色、上一任务和已加载技能。

```json
{
  "agent_type": "search_agent",
  "agent_id": "search_agent",
  "task_id": "verify_versions",
  "task": "继续使用已读取的官方资料，核对尚未确认的版本差异，并保留来源。"
}
```

`agent_id` 取自 `reusable_agents`，标识要续用的检索 Agent。`task_id` 标识新任务，省略时由后端生成。同批任务若依赖这个示例任务，可以传 `"blocked_by": ["verify_versions"]`。

## 状态与边界

- 支持 `search_agent` 和 `local_search_agent`；角色、资料快照和访问策略必须与原 Agent 兼容。
- 保留同一 Agent ID、thread、对话历史与浏览器状态，包括原有页面引用和本地阅读上下文。
- 继承已加载技能包的固定版本，适用时直接执行；来源或能力要求改变时再发现和加载。每次执行仍检查技能可用性和访问策略。
- 每次派发建立独立 TaskContext、抽取队列、进度检测和执行预算，历史证据不会因复用自动改绑。会话总预算和并发上限继续生效，续派不消耗新 Agent 创建额度。
- 技能工作目录和调用回执按任务隔离，避免新任务重放旧执行结果。需要旧原文支持新结论时，应重新读取或按已有证据复用规则处理。
- 每个任务独立提交报告；复用同一 Agent 时，运行时保留尚未交付的旧报告。

正在执行的 Agent 不接受新的指定派发。同一批中给空闲 Agent 排入多个任务时，调度器逐个执行。取消后仍在收尾的 Agent 继续占用容量；存在未完成 checkpoint 的 Agent 不接受续派。

复用仅限当前进程中同一次 Orchestrator 运行。服务重启或新运行不会恢复内存中的 Agent registry。使用自定义 middleware、额外工具或直接 steering 的专用 Agent 不在此续派范围内。指定的 Agent 不可用时返回原因，不静默创建替代 Agent。
