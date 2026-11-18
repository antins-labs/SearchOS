# Agent 工具目录

工具按职责组织，短小完整实现使用单文件，多文件类别由包入口声明可调用工具；工具名称、说明和参数由 `@tool` 定义，角色工具集由 Agent 装配层选择。

| 类别 | 实现位置 | 职责 |
|---|---|---|
| 表格 | `schema/tables.py` | 建表、增改列、约束校验、观测重放及完整表读取 |
| 表格 | `schema/rows.py` | 行增删改、主键重命名、恢复和有来源的值写入 |
| 表格 | `schema/cells.py` | 值归一、推断值、来源核验与单元格证据投影 |
| 任务 | `tasks/queue.py` | Frontier 入队、范围与预算校验、取消 |
| 任务 | `tasks/reports.py` | 等待执行或追问、回收报告、汇总调度反馈 |
| 任务 | `tasks/evidence.py` | 任务证据关联与观测重放 |
| 状态读取 | `socm_read/` | Coverage、Evidence、Frontier 与执行报告的只读窗口 |
| 写作 | `writer.py` | 提纲、章节、引用及草稿镜像 |
| 技能 | `skills/catalog.py` | 技能发现、权限过滤与失败记忆读取 |
| 技能 | `skills/execution.py` | 固定版本、加载、资源读取与受限执行 |
| 技能 | `skills/capability.py` | 将 Access Skill 注册为宿主桥能力 `skill.call` |
| 执行 | `exec/` | 通用程序、计算、持久文件与宿主能力桥；沙箱内 `searchos_sdk` 调用已注册能力；主 Agent 离线，Search 按来源权限联网 |
| 浏览器 | `simple_browser/` | 搜索、页面窗口、视觉读取、缓存与后端 |

根目录 `search_state.py` 只保存共享 ContextVar：工作区、Agent、任务、表和来源范围。所有类别使用同一组对象；移动工具实现时不能重新声明这些变量。

## 工具描述

第一段写清模型何时调用工具、工具执行什么动作、返回什么结果。角色提示词使用这一段列出可用工具。容易混用的工具要说明选择条件，例如空闲时用 `check_agents` 等下一份报告，查看任务列表用 `list_frontier`。这套约定参考了 [OpenAI 的函数定义指南](https://developers.openai.com/api/docs/guides/function-calling#best-practices-for-defining-functions)。

函数工具用 `@tool(parse_docstring=True)` 解析 Google 风格的 `Args:`。每个参数说明取值含义，按需注明格式、单位、默认行为或与其他参数的关系。显式 Pydantic 模型在 `Field(description=...)` 中写字段说明，直接声明 JSON Schema 的工具在对应属性写 `description`。

把已有示例放在相关参数说明里。跨参数示例可放在工具正文中，尤其要保留复合主键、JSON 字符串、多行任务和分页续读等容易写错的用法。验证时检查 `convert_to_openai_tool` 的实际输出，确认示例可见、每个公开参数都有说明。

## 入口与依赖

- 调用方优先从所属类别入口获取工具，例如 `from searchos.tools.schema import create_schema`。
- 任务工具从 `searchos.tools.tasks` 获取；技能工具从 `searchos.tools.skills` 获取；执行工具从 `searchos.tools.exec` 获取。
- 类别目录提供工具不代表每个 Agent 都能调用全部工具。角色集合仍由 `searchos/agents/` 装配，不能把目录中的所有工具自动注册给主 Agent。
- `tasks/queue.py` 单向使用 `reports.py` 的反馈格式；二者共用现有运行时和调度器，不各自创建状态。
- 技能目录不依赖执行模块；`skills/__init__.py` 组合工具。路径核验位于 `searchos/skills/runtime/paths.py`，技能执行与浏览器结果页面共同使用。
- `simple_browser/tools.py` 集中搜索、打开、查找、视觉读取与批量探索入口。`session.py` 管理会话、来源规则和技能结果页面，保留结果、fixture、诊断和索引分类。`pages.py` 负责渲染，`images.py` 负责图片与 PDF；抓取缓存和运行计量统一在 `fetchers/cache.py`。只有实际阅读的合格结果窗口进入 Evidence Extraction。

新增文件按实际职责划分，不按一个工具一个文件机械拆分。测试替换依赖时定位实现所属文件，避免在包入口伪造第二份状态。迁移与验证记录见 [工具目录重构](../../docs/tools-architecture-20261017.zh.md)。
