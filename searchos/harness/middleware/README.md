# Middleware 目录导航

使用组件先看 [Middleware 用途与用法](USAGE.md)，包含全部公开组件的用途和初始化示例。更多组合规则见 [组合与生命周期说明](../../../docs/middleware-composition.md)。默认组合在 `pipelines.py`，实际钩子在各目录的 `*_middleware.py`。

```text
middleware/
├── __init__.py                 # 公开组件与 pipeline 导出
├── models.py                   # TaskContext、SourceContext
├── pipelines.py                # 默认网页、本地、探索、写作和调度组合
├── tool_costs.py               # 工具工作量计量
├── context/
│   ├── *_middleware.py         # 上下文与工具结果功能
│   ├── core/                   # 窗口裁剪、历史压缩、搜索轮次和任务视图
│   └── utils/token_counts.py   # 模型窗口与 token 计量
├── extraction/
│   ├── *_middleware.py         # Web、Local、最终摘要
│   ├── base.py                 # 来源组件共有的提交与反馈
│   └── core/                   # 协调、来源、窗口、表格抽取、提交与存储
├── sensor/
│   ├── *_middleware.py         # 检测、预算、路线检查与进展
│   ├── core/                   # 检测算法、内部适配、ControlState、BudgetState
│   └── utils/tool_outcomes.py  # 新旧工具回执归一化
└── utils/messages.py           # 系统消息合并、反馈、阻断结果与上下文消息
```

基类按所属层就近放在 `base.py`。Extraction 的 `ObservationMiddleware` 留在根目录，Sensor 的 `Sensor` 与 `_SensorMiddleware` 留在 `core/base.py`。Context 出现共用基类时再创建 `base.py`。

仅供同一入口使用的简短辅助函数在该文件内私有化，例如最终摘要的观测构造。Context 的裁剪与压缩共用 `core/history.py` 中的完整工具事务划分；派发额度、轮次停滞与 Writer 触发统一位于 `sensor/core/dispatch.py`。

跨领域基础模型与 JSON 解析统一放在 `searchos/utils/`；表格和无表抽取从 [json_extract.py](../../utils/json_extract.py) 共用严格对象数组解析。

一个可独立选择的功能对应一个组件；同一功能的内部步骤不拆成公开 middleware。复杂领域实现归 core；同一概念的记录类型与辅助函数放在一起，不为短小内部实现单独增加目录。跨功能的辅助函数归 utils，短小私有函数留在使用它的文件内。不再有 profiles、Assembly、公开 barrier、execution 或 telemetry 功能分类。

运行设施由所属模块管理：

| 职责 | 实现 |
|---|---|
| 模型调用、图片兼容、控制信号执行和资源收尾 | [agents/execution.py](../../agents/execution.py) |
| 系统消息合并和工具消息操作 | [utils/messages.py](utils/messages.py) |
| Explore 轮次策略 | [agents/explore/policy.py](../../agents/explore/policy.py) |
| Orchestrator 运行池提醒 | [agents/orchestrator/policy.py](../../agents/orchestrator/policy.py) |
| session 轨迹和上下文记录 | [telemetry/recording.py](../telemetry/recording.py) |
| 通用 API Usage、运行计量与日志 | [telemetry/usage.py](../telemetry/usage.py) |

这些设施不属于公开 middleware；图入口负责接入。

Context 新增 [CompactionContextMiddleware](context/COMPACTION_CONTEXT.md)：阈值触发、续接摘要和 checkpoint 持久化；显式装载后启用。
