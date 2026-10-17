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
| Frontier Task、研究计划、重试和失败记忆 | `planning/` |
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

## 内部路径迁移

原 `frontier`、`research_plan`、`retry_routes`、`strategy` 进入 `planning/`；`workspace`、`persistence` 进入 `storage/`；`conflicts` 进入 `coverage/`；`provenance`、`values` 进入 `evidence/`。仓库调用已同步修改，不保留旧模块转发文件。状态 JSON 格式和既有领域入口保持不变。
