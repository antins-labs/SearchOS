# Agent 工具目录

每类工具使用独立目录。包入口声明可调用工具，内部文件按职责组织实现；工具名称、说明和参数由 `@tool` 定义，角色工具集由 Agent 装配层选择。

| 类别 | 实现位置 | 职责 |
|---|---|---|
| 表格 | `schema/definitions.py` | 建表、加列、约束校验及建表后的 Explore 回放 |
| 表格 | `schema/entities.py` | 行增删改、主键归一和有来源的值写入 |
| 表格 | `schema/evidence.py` | 完整表读取、已有证据的来源核验与单元格投影 |
| 表格 | `schema/assertions.py` | 共用上下文访问、值归一与证据写入规则 |
| 任务 | `tasks/queue.py` | Frontier 入队、范围与预算校验、取消 |
| 任务 | `tasks/reports.py` | 等待执行或追问、回收报告、汇总调度反馈 |
| 任务 | `tasks/evidence.py`、`tasks/plan.py` | 任务证据关联、观测重放与研究计划 |
| 状态读取 | `socm_read/` | Coverage、Evidence、Frontier 与执行报告的只读窗口 |
| 写作 | `writer/outline.py` | 提纲、章节、引用及草稿镜像 |
| 技能 | `skills/catalog.py` | 技能发现、权限过滤与失败记忆读取 |
| 技能 | `skills/execution.py` | 固定版本、加载、资源读取与受限执行 |
| 技能 | `skills/legacy.py` | 旧 typed-tool Adapter 的兼容实现 |
| Python | `python/tool.py` | 通过现有执行后端运行有界离线代码 |
| 浏览器 | `simple_browser/` | 搜索、页面窗口、视觉读取、缓存与后端 |

根目录 `search_state.py` 只保存共享 ContextVar：工作区、Agent、任务、表和来源范围。所有类别使用同一组对象；移动工具实现时不能重新声明这些变量。

## 入口与依赖

- 调用方优先从所属类别入口获取工具，例如 `from searchos.tools.schema import create_schema`。
- 研究计划从 `searchos.tools.tasks` 获取；技能工具从 `searchos.tools.skills` 获取；Python 工具从 `searchos.tools.python` 获取。
- 类别目录提供工具不代表每个 Agent 都能调用全部工具。角色集合仍由 `searchos/agents/` 装配，不能把目录中的所有工具自动注册给主 Agent。
- `tasks/queue.py` 单向使用 `reports.py` 的反馈格式；二者共用现有运行时和调度器，不各自创建状态。
- 技能目录不依赖执行模块；`skills/__init__.py` 组合工具。路径核验位于 `searchos/skills/runtime/paths.py`，技能执行与浏览器结果页面共同使用。
- `simple_browser/result_pages.py` 统一技能结果页面，保留结果、fixture、诊断和索引分类。只有实际阅读的合格结果窗口进入 Evidence Extraction。

新增文件按实际职责划分，不按一个工具一个文件机械拆分。测试替换依赖时定位实现所属文件，避免在包入口伪造第二份状态。迁移与验证记录见 [工具目录重构](../../docs/tools-architecture-20261017.zh.md)。
