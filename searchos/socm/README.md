# SOCM 目录与写入规则

`SearchState` 聚合 Frontier、Evidence Graph、Coverage Map 与 Failure Memory；`WorkspaceManager` 负责持久化和事务。按修改对象查找实现：

| 修改内容 | 位置 |
|---|---|
| 状态字段、预算、大纲、Agent 报告 | `state.py` |
| 表结构、行身份、单元格、列约束 | `coverage/models.py` |
| 证据可见性、优先级、目标格投影 | `coverage/projection.py` |
| 证据提交、绑定、清空、覆盖状态刷新 | `coverage/commit.py` |
| 单元格冲突的复核结果与状态 | `coverage/conflicts.py` |
| 事实节点、图关系、来源观测、任务证据关联 | `evidence/graph.py` |
| 原始来源地址和答案引用 | `evidence/provenance.py` |
| 缺失值识别 | `evidence/values.py` |
| Frontier Task、研究计划、精确调用重试 | `planning/` |
| 四类失败模型、观察提取、原子记录、复盘与投影 | `failure_memory/` |
| 工作区目录、文件锁、原子状态更新 | `storage/workspace.py` |
| 文件版本与不可变字节快照 | `storage/persistence.py` |
| 状态摘要、角色视图和溯源展示 | `views/` |

## 依赖与入口

调用方可从 `searchos.socm` 获取主要模型和 `WorkspaceManager`；`searchos.socm.coverage` 与 `searchos.socm.evidence` 提供各领域的稳定入口。内部实现直接导入所属模块，避免通过包入口形成循环依赖。

Coverage 模型依赖事实类型；只读投影依赖模型；提交依赖模型、投影和冲突规则。`SearchState` 在最上层聚合这些模型。只用于类型注解的聚合状态放在 `TYPE_CHECKING` 下；确实需要延迟求值的状态操作保留函数内导入。

## 一次修改如何发布

`commit_evidence`、`commit_table_facts` 和 `bind_cell_evidence` 修改传入的内存状态，不自行取得文件锁。持久化修改须在 `WorkspaceManager.atomic_update_state` 内完成，使事实、任务关联和单元格投影在同一次状态更新中发布。

```python
from searchos.socm.coverage import commit_evidence

def apply(state):
    commit_evidence(state, candidates)
    return state

workspace.atomic_update_state(apply)
```

读取或渲染使用 `answer_evidence` 与 `project_cell_evidence`，保持来源范围、行排除和单元格绑定语义一致。文件快照只缓存不可变字节；每次解码返回独立对象，不能把可变 `SearchState` 当作跨事务缓存。

## 大表读取与抽取

CoverageMap 保存完整数据。调度与写作概览每表最多展示 30 个缺口实体，统计覆盖全部数据字段；显式 Search 任务保留全部分配目标。完成状态要求值和证据比较均已确定，不可获取字段及待比较证据单列。默认窗口优先展示尚未分配的可处理字段，查询不会预留任务。

Main Agent 优先使用最新 SOCM 更新。需要查看窗口外的行、字段或来源时，调用 `inspect_table`，返回 `{table_id, primary_key, columns, summary, rows, count, total_matched, next_cursor}`。每行按 `columns` 排列，前几列是按 `primary_key` 顺序排列的键值。`with_values=true` 返回页内完整原值，`false` 返回字段状态。需要引用时，传 `row` 和 `with_values=true`，可用 `attribute` 指定一列。每页默认 30 行，字符预算按整行分页。游标绑定筛选条件并按稳定实体键推进。任务改变表格后，需继续查询时从头扫描。Main Agent 负责规划批次，超大任务继续接受。相同分派范围的部分重叠会返回目标键及任务 ID。

抽取根据任务目标生成最多 200 个实体的窗口，逐窗口提交证据；多个窗口共享已获取的来源内容。失败或取消保留已提交结果，并使用现有观测日志恢复。导出始终读取完整 CoverageMap，覆盖所有行及未完成字段。

角色视图和抽取上下文使用一次列名表头，后续每行按列顺序展示值。`null` 表示缺失；冲突、待比较、候选值和不可获取状态附在对应单元格。显式任务展示目标实体的各字段，分配范围使用从零开始的行列下标标注。发现视图的最近行窗口跳过已展示的缺口行。抽取输出继续使用逐字段的 JSON 行对象。

建表、添加实体和抽取提交接收逐字段的行对象，将主键原值写入各自的单元格。展示、证据校验及导出通过 `CoverageMap.primary_key_values` 读取。

## 行与单元格引用（v2）

`refs.py` 集中定义引用与编解码。工具使用 `RowRef = {table_id, key}` 和 `CellRef = {table_id, key, attribute}`；`key` 始终是按 `primary_key` 顺序排列的字符串数组。缺少任一主键值会拒绝写入。字段内的 `|`、斜线、句点、引号和换行保持原值。

例如，表 `products` 的行以 `["Acme|EU","Classic"]` 为键，行引用为 `{"table_id":"products","key":["Acme|EU","Classic"]}`。增加 `"attribute":"Size"` 即可得到该行 Size 列的单元格引用，用于 `enqueue_tasks.target_cells`、`read_evidence` 和 `project_evidence.projections`。`edit_entities` 接收 `{row, rename?, restore?, set?}`，其中 `rename` 提供完整的新主键数组。删除使用 `remove_entities(rows=[RowRef], reason=...)`，恢复使用 `edit_entities` 的 `restore=true`。

`set` 按字段指定值和支持它的已有证据，例如 `{"Size":{"value":"500ml","evidence_ids":["f_size"]},"Aroma":null}`。Main 先通过 `read_evidence` 阅读原文摘录并判断语义支持，格式修改沿用原证据 ID，计算写回列出全部必要输入的证据 ID。工具验证证据有效状态、原文地址、摘录、来源范围及字段约束，再更新单元格绑定；原始事实保持不变。接口不接受手填 `source`、`source_excerpt`，不创建编辑证据节点。

空值和 `/` 共用 `is_missing_value` 规则，清空后保持 `missing`，不计为完成；`set` 中直接传 `null` 或传 `{"value":null}` 均可，清空无需证据 ID。被移除的绑定保留审计状态，共享证据在其他单元格中的用途保留。未知事实使用 `null`，缺失原因写入回答。字段校验失败时保留原值，并返回对应错误；`updated` 仅列出至少有一项成功编辑的行。

内部行键为主键数组的紧凑 JSON，单元格键为 `[table_id, key, attribute]` 的紧凑 JSON。统一保留 Unicode，禁用额外空格；前端 `socmRefs.ts` 使用相同编码。实体比较逐字段规范化，重命名在同一状态事务中更新单元格、证据、任务和失败范围。分页游标绑定格式版本与筛选条件。

研究计划的 `expected_members` 同样使用 `RowRef`；每个集合范围只对应一张表。成员核对返回结构化的缺失成员和额外成员，尚未发现的预期成员继续保留。

持久化状态使用 `format_version: 2`。运行时只读取新引用格式。需要继续使用的旧工作区先离线迁移：

```sh
.venv/bin/python -m searchos.socm.migrate_refs OLD_WORKSPACE NEW_WORKSPACE --report /tmp/socm-migration.json
```

迁移预检当前状态、结构化轮次快照和待抽取记录，优先读取保存的主键单元格。全部通过后原子发布新工作区目录；原工作区、轨迹、对话和来源文件保持原样。歧义或缺失引用写入修复报告，发布中止。新目录可作为续跑工作区；原目录用于核对历史数据。

停止后端后，可添加 `--replace`，此时第二个路径用于保存原目录备份。程序先构造并验证完整新目录，再安装到原工作区路径；安装失败会恢复原目录。迁移失败的工作区保留原始文件，需根据报告修复后再迁移。

## 内部路径迁移

Frontier、研究计划与重试路线位于 `planning/`；工作区与快照位于 `storage/`；冲突位于 `coverage/`；来源与值处理位于 `evidence/`。失败记忆独立位于 `failure_memory/`。调用方直接使用所属领域入口，不保留旧模块转发文件。

## Failure Memory

失败记忆只保存能够改变搜索选择的 `query`、`source`、`skill`、`path` 经验。`failure_memory/models.py` 定义记录，`extraction.py` 从可信工具元数据提取确定事实，`post_mortem.py` 根据本次任务的实际工具与阅读轨迹提炼经验，`projection.py` 按角色与目标投影。

调用 `record_failure(workspace, memory)` 统一写入；需要与任务状态同步发布时，在已有原子事务中调用 `state.failure_memory.record(memory)`。调用方固定 task、attempt、来源权限、目标格、操作与 observation ID；回放不增加观察次数。记忆只提供局部事实与带置信度的建议，不隐藏整个技能或封禁域名。

检索 middleware 只负责采集适配，内部提取与存储属于 SOCM。参数、模型、预算、取消和抽取内部错误不形成失败记忆；重复与停滞只触发检查。查询有候选时，复盘必须关联实际阅读；路径需要不同操作及阅读或明确负结果。技能限制保留具体版本。

存储统一为 `SearchState.failure_memory.records`。旧 `strategy_log` 仅读取时转换，移除 `claim`、单纯重复/停滞和无法恢复准确来源或技能版本的记录；新写出不再保留旧字段。旧 `planning/strategy.py` 与 Orchestrator post-mortem 执行链已删除。详细过程见 [开发记录](../../docs/development/failure_memory.md)。
