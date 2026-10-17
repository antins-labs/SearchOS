# 代码架构审查与重构

日期：2026-10-16。

## 范围与原则

本次审查覆盖 `searchos/`、Web 后端与前端，以及它们的调用和测试。检查方法包括目录与文件体量统计、Python 导入和重复函数扫描、前端入口可达性、全仓引用复核及行为测试。技能库、历史快照和命令行 worker 有动态加载入口，不能按“没有静态 import”删除；论文、实验产物及现有未提交开发内容保留。

当前维护困难来自两种不同现象：Web 后端把多个领域的实现平铺在包根目录；部分核心模块（Module）又同时承担运行、状态结算和报告生成。前者可以按职责归档，后者需要先明确状态和并发规则。目录层数或文件数量本身不作为拆分依据。

本轮以保持现有调用约定（Interface）为约束，使同一职责的实现集中（Locality）；HTTP 路径、工具名称、存储格式和历史技能兼容入口保持稳定。内部 Python 导入统一迁到新路径，不增加旧路径转发文件；已有领域入口可由包的 `__init__.py` 继续提供。

## 审查发现与实施方案

### 1. Web 后端的领域归属不清

`web/api/` 根目录有 13 个 Python 文件，配置存储、技能包读取、技能创建和资料库作业混在一起。`routes/` 已经承载 HTTP Adapter，其他实现应按职责集中。

| 原路径（相对 `web/api/`） | 目标路径 |
|---|---|
| `settings_store.py`、`settings_views.py` | `settings/store.py`、`settings/views.py` |
| `skills_catalog.py`、`skill_library.py` | `skills/catalog.py`、`skills/library.py` |
| `skill_creation_jobs.py`、`skill_creation_drafts.py` | `skills/creation.py`、`skills/drafts.py` |
| `local_index_jobs.py`、`network_import_jobs.py`、`topic_recap_jobs.py` | `local/index_jobs.py`、`local/import_jobs.py`、`local/recap_jobs.py` |
| `routes/search.py` 内请求与响应模型 | `research/contracts.py` |

调用和测试一并更新。技能目录定位改用统一仓库根路径，避免迁移后 `__file__.parents` 层级变化导致读错目录；同时纠正原资产读取把相对技能路径解析到 `web/` 的问题。Assistant 调度只为 `SourcesRequest` 引入整份路由的依赖改为直接读取契约；完整运行启动逻辑仍保留现有语义。

### 2. Search Episode 过度分层

`context/core/models.py` 只有两个记录类型；类型、解析和渲染分散在三个位置。它们没有独立 Adapter 或变化 Seam。将记录类型与 `context/utils/episodes.py` 合并到 `context/episodes.py`，middleware 从这一处读取，实现与验证集中。其他上下文辅助模块各有真实职责，保留。

### 3. 共享规则被复制维护

报告 `synthesis.py` 与评测 `eval_table_export.py` 重复实现单元格证据投影、失效证据过滤、主键读取和关系连通分组。统一放入内部 `report/tables.py`，两个呈现路径共用。两套 join 的空值规则、评测无损回退和仅主键父表优化存在语义差异，本轮不机械合并。

本地索引、资料库、阅读器与迁移代码有三份原子文本写入和六份分块文件 SHA256。收拢为 `local/storage_io.py`，保持同目录临时文件、flush/fsync、原子替换及失败清理语义。调用方不再跨模块导入 `document_store` 的私有写入函数。

### 4. 可删除的冗余代码

以下候选经引用和入口核对后清理：

- 核心：`get_agent_spec`、`task_anchor_index`、`get_schema_tools`、浏览器渲染 `_truncate`、无入口的 `render_skill_sets`。
- 本地文档：未使用的 `StageState`、`PipelineStages`、`GenerationFingerprint` 和 `_sanitize_answer`；当前流水线使用分阶段 fingerprint 与流式引用绑定。
- Web：未使用的 `get_llm`、`effortGuidance.ts`、`retryNetworkImport`、`listSkillLibrary`、`ROOT_DOCUMENT_GROUP`。
- 前端：仅转发 `ui/Select` 的 settings 控件文件，以及五个无引用的 Next 模板 SVG。

明确保留：旧 Executor 的 `SkillContext`、运行 worker、迁移模板、`agent_legacy.md`、兼容测试使用的技能 Adapter。`local/parsers/` 中不同文件格式具有不同实现，不能因为文件较多就合并。

### 5. SOCM 按状态职责组织

根据用户补充，本轮进一步整理 SOCM。原根目录的 13 个 Python 文件把结构、证据、规划和存储放在同一层；`coverage.py` 的 1154 行同时包含模型、读取与提交。按领域组织后，根目录只保留统一入口和 `SearchState` 聚合状态。

```text
socm/
├── __init__.py             # 既有公开导出
├── state.py                # 聚合状态、预算、报告与大纲
├── coverage/
│   ├── models.py           # 表格、单元格及 CoverageMap
│   ├── projection.py       # 证据可见性、优先级和只读投影
│   ├── commit.py           # 证据提交、绑定、清空与刷新
│   └── conflicts.py        # 单元格冲突判定结果的状态投影
├── evidence/
│   ├── graph.py            # 事实图、来源观测和任务证据关联
│   ├── provenance.py       # 来源地址与答案引用解析
│   └── values.py           # 缺失值判定
├── planning/
│   ├── frontier.py         # Frontier Task
│   ├── research_plan.py    # 研究计划与集合复核
│   ├── retry_routes.py     # 重试路线与结果
│   └── strategy.py         # Failure Memory
├── storage/
│   ├── workspace.py        # 工作区与原子状态事务
│   └── persistence.py      # 有界文件快照缓存
└── views/                  # 保留现有视图
```

保留 `searchos.socm`、`searchos.socm.coverage`、`searchos.socm.evidence` 的领域入口；存储与规划的内部调用改用明确路径。模型不依赖提交层，读取不触发写入，提交通过现有工作区事务发布。原有延迟导入按依赖需求保留，不把状态聚合根引入模型层。验证覆盖公开导出、Pydantic 状态 schema、证据提交、冲突、来源范围、旧快照恢复、工作区锁与性能缓存。

同时清理调用端对已删除 `AgentReport` 的两处引用。缺失运行注册信息时，先按持久化归属回收运行任务，再按派发角色登记现有 Search/Writer/Explore 错误报告，使 `check_agents` 能返回具体错误。回收事务复核归属，防止误改已派给其他 Agent 的任务；写入失败时不登记完成，保留后续僵尸任务恢复路径。Writer 自动派发补齐已有任务 ID 的持久绑定。历史任务若既未持久化归属、又已丢失注册信息，仍无法可靠恢复归属。

目录与写入规则见 [SOCM 导航](../searchos/socm/README.md)，Web 后端导航见 [API 目录](../web/api/README.md)。

## 后续设计，未纳入本轮变更

| Module | 现有困难 | 建议拆分及先决验证 |
|---|---|---|
| `agents/orchestrator/lifecycle.py` | spawn、continue、collect、报告和失败回收集中在 1693 行 | 将任务结算形成内部 Module；先固定原任务 ID、证据归属和 Frontier Task 更新规则 |
| `harness/session.py` | 运行循环与停止后报告生成集中在 1665 行 | 将 finalization 移入 `harness/report/`；覆盖追问、超时与取消后收尾 |
| `tools/schema.py` | 结构编辑与事实投影混合 | 按结构编辑和证据投影划分实现，保留现有工具 Interface |
| `local/library.py` | 资料库、主题、问答和引用解析混合 | 以授权、版本核验和引用绑定的现有 Interface 集中实现 |
| Web research / Assistant | 运行层仍调用路由启动和历史处理函数 | 提取研究运行与历史快照 Module，由应用启动层接入 Assistant 生命周期 |
| 前端 Settings | Page 与 Modal 重复注册分区与标签 | 统一类型化分区目录，验证桌面与移动布局 |

这些工作涉及状态所有权或产品流程，后续应单独执行行为重构；本轮不通过搬动大段函数隐藏耦合。

2026-10-17 进展：工具分类归档以及 `schema`、`tasks` 的职责拆分已完成，见 [工具目录重构](tools-architecture-20261017.zh.md)。其余后续项仍保持上表状态。

## 验证记录

### 结构与兼容性

- SOCM 根目录 Python 文件由 13 个减至 2 个；Web API 根目录由 13 个减至 4 个。新增目录导航说明修改对象、依赖和写入规则。
- SOCM 的 104 个原有顶层定义经 AST 对照，除导入路径外实现体一致；39 个根入口导出以及 `SearchState`、`CoverageMap`、`TableSchema` 的 JSON schema 保持一致。
- 覆盖全部 23 个 SOCM 模块的独立进程导入，以及正序、逆序导入均通过；双表共享证据的旧快照恢复与重复提交结果保持一致。
- Web 完整 OpenAPI 对比一致，共 90 个路径。技能包相对目录新增回归，验证资产读取与运行执行均以仓库根路径解析。
- 本地原子写入新增失败回归，覆盖 fsync、replace 失败时原文件保留与临时文件清理。
- 重构结束时，原有 10 个已修改跟踪文件的 diff 与开始前逐字节一致。

### 测试结果

后端使用项目 `.venv/bin/python`，显式传入 `-c pyproject.toml --rootdir=.`；最终全量执行另加 `--asyncio-mode=auto`，避免现有未标注异步测试被 strict 模式拒绝。全量排除原有无法收集的 `tests/test_preprocess_cache.py`。

| 检查 | 结果 |
|---|---|
| 修改前后端基线 | 1340 通过、18 失败、12 跳过、42 fixture 错误 |
| 重构后后端全量 | 1428 通过、14 失败、12 跳过；失败均已存在于基线 |
| 前端测试 | 145 通过 |
| Agent 报告与调度回归 | 65 通过；包含 36 个缺注册回归用例，验证真实 Frontier、Scheduler、任务改派与写入失败恢复 |
| TypeScript | `tsc --noEmit --incremental false` 通过 |
| 本轮 Python 文件静态检查 | Ruff F 规则通过 |
| 补丁检查 | `git diff --check` 通过 |

Web 设置测试原来启动真实 Assistant 运行目录，与正在运行的 worker 锁冲突，产生 42 个 fixture 错误。本轮改为临时运行目录和受控后台作业；另 4 个异步测试在 auto 模式下通过。这些数量变化不代表修复了 46 个产品缺陷。

### 既有失败与限制

`tests/test_preprocess_cache.py` 仍导入不存在的 `eval.preprocess.PreprocessCache`，普通全量收集会中断。本轮没有删除该测试或恢复这项历史功能。其余 14 项失败如下，均在改动前出现：

| 测试文件／用例 | 当前失败原因 |
|---|---|
| `test_access_builder_contract` 的 generated package 用例 | 当前沙箱禁止本机端口操作 |
| `test_access_validation_feedback`、`test_site_skill_creation` 的 site entry 用例、`test_skill_proxy_routing` | 内层 `sandbox-exec` 无法启动，执行返回 blocked |
| `test_local_service` 的 occupied port 用例、`test_skill_browser_auth` 的前两个用例 | 本机监听被当前环境拒绝 |
| `test_skill_browser_auth` 的 sandbox search 用例 | 宿主 Playwright/Chromium 不可用 |
| `test_skill_command_runtime` 的 network environment 用例 | 代理端口预期与当前进程环境不一致 |
| `test_evidence_commit` 的 overwrite 用例 | 旧测试写非空单元格时未提供当前契约要求的原始来源及片段 |
| `test_local_search_agent` 的默认 orchestrator 用例 | 旧断言要求 prompt 不含 hybrid，与当前计划说明不符 |
| `test_site_skill_creation` 的 advice/resume 用例 | 恢复会话 host 与请求不匹配 |
| `test_skill_creation` 的 task intent 用例 | 预期复用技能未出现在当前目录结果 |
| `test_skill_library_migration` | 部分已有技能的运行脚本与当前标准模板不同 |

这些失败尚未解决；当前证据支持“本轮测试未发现新增失败”，不等于全量测试全部通过。需要真实宿主浏览器、端口和独立沙箱执行的行为，也不能用本轮受限环境测试确认。

### 测试目录的版本管理

2026-10-17 按用户要求，将根目录 `/tests/` 加入 `.gitignore` 并取消已跟踪测试文件的跟踪，保留本地文件。以上后端验证基于本地测试目录；后续从仓库重新检出时不会包含该目录。`web/frontend/tests/` 保持跟踪。
