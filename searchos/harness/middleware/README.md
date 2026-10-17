# Middleware 目录导航

使用组件先看 [Middleware 用途与用法](USAGE.md)，包含全部公开组件的用途和初始化示例。更多组合规则见 [组合与生命周期说明](../../../docs/middleware-composition.md)。默认组合在 `pipelines.py`，实际钩子在各目录的 `*_middleware.py`。

```text
middleware/
├── __init__.py                 # 公开组件与 pipeline 导出
├── models.py                   # TaskContext、SourceContext
├── pipelines.py                # 默认网页、本地、探索、写作和调度组合
├── context/
│   ├── *_middleware.py         # 上下文与工具结果功能
│   ├── episodes.py             # Episode 记录、解析与历史渲染
│   └── utils/                  # 消息裁剪、压缩与投影
├── extraction/
│   ├── *_middleware.py         # Web、Local、最终摘要
│   ├── base.py                 # 来源组件共有的提交与反馈
│   ├── core/                   # 协调、路由、准备、抽取、提交与存储
│   └── utils/                  # 摘录定位、数值支持与单位换算
├── sensor/
│   ├── *_middleware.py         # 检测、预算、路线检查与进展
│   ├── core/                   # 检测算法、内部适配、ControlState、BudgetState
│   └── utils/queries.py        # 查询归一化
└── utils/
    ├── messages.py             # 反馈、阻断结果与上下文消息
    └── tools.py                # 工具工作量计量
```

一个可独立选择的功能对应一个组件；同一功能的内部步骤不拆成公开 middleware。复杂领域实现归 core；同一概念的记录类型与辅助函数放在一起，不为短小内部实现单独增加目录。跨功能的辅助函数归 utils，短小私有函数留在使用它的文件内。不再有 profiles、Assembly、公开 barrier、execution 或 telemetry 功能分类。

运行设施由所属模块管理：

| 职责 | 实现 |
|---|---|
| 控制信号执行、资源收尾和框架钩子适配 | [agents/execution.py](../../agents/execution.py) |
| 模型调用与图片兼容 | [agents/model_call.py](../../agents/model_call.py) |
| Explore 轮次策略 | [agents/explore/policy.py](../../agents/explore/policy.py) |
| Orchestrator 运行池提醒 | [agents/orchestrator/policy.py](../../agents/orchestrator/policy.py) |
| session 轨迹和上下文记录 | [telemetry/recording.py](../telemetry/recording.py) |

这些设施不属于公开 middleware；图入口负责接入。

Context 新增 [CompactionContextMiddleware](context/COMPACTION_CONTEXT.md)：阈值触发、续接摘要和 checkpoint 持久化；显式装载后启用。
