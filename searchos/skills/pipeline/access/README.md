# Access Pipeline 开发入口

Access Pipeline 接收站点需求，经过规划、开发、验收和修复，交付带逐能力状态的 Portable Skill。先读 `pipeline.py` 的 `build_skill()` 和 `AccessPipeline.validate()`，再进入对应功能模块。

## 代码按职责组织

```text
access/
├── pipeline.py                 # 构建入口、角色交接、验收调度、草稿恢复与交付
├── agents/
│   ├── planner.py              # 站点探索循环、计划契约与澄清
│   ├── builder.py              # 开发与修复循环、Builder 工具分发
│   ├── validator.py            # 独立验收循环、业务执行与语义提交
│   └── prompts/{planner,builder,validator}.py
├── validation/
│   ├── checks.py               # 静态预检、同次执行与 JSON 检查、宿主固定样例检查
│   └── progress.py             # 函数索引、复验范围、结果复用、原输入补验
├── tools/
│   ├── web.py                  # 互联网 search/find/open
│   ├── files.py                # 候选文件、只读快照、分页读取与局部编辑
│   └── execute.py              # 探测代码和 CLI 的统一执行入口
├── session.py                  # 历史压缩、剩余预算、收尾控制
└── artifacts.py                # 构建日志、完整输出落盘、分页和脱敏快照
```

工具定义与实现放在对应模块；角色可用的工具集合在 Agent 处组装。三个 Agent 的常规 LLM 调用预算默认均为 50。修改能力计划看 Planner，修改开发提示词看 `agents/prompts/builder.py`，修改机器判定看 `validation/checks.py`，修改增量策略和失败补验看 `validation/progress.py`。

## 主流程和输入输出

| 步骤 | 输入 | 执行者与输出 |
| --- | --- | --- |
| 创建或恢复 | host、URL、需求、可选旧包或草稿 | `build_skill()` 建临时候选，恢复文件、计划和验收记录 |
| 研究规划 | 站点与用途 | `SitePlannerAgent.prepare()` 输出业务能力、验收要点、研究依据、依赖与限制 |
| 开发 | 计划、研究、候选文件、剩余预算、静态缺项 | `AccessBuilderAgent.run()` 自主设计接口与输出、编写代码和 SKILL.md；提交当前候选交验 |
| 固定候选 | 文件指纹、计划和上次报告 | `AccessPipeline.validate()` 创建只读快照，运行静态预检；`ValidationProgress` 选择本轮待验能力 |
| 独立执行 | 固定候选、待验范围、原正常业务失败输入 | `ValidationAgent.validate()` 使用 read_file/exec/send_message；框架检查同次 CLI 结果 |
| 提交与合并 | 执行观察、机器结果、语义结论 | `ValidationReview.submit()` 检查证据与原输入补验；`ValidationProgress.merge_report()` 合并本轮与复用结果 |
| 修复或交付 | 逐能力报告、函数位置、修复额度 | Builder 在同一循环读取并修复；结构有效的候选按逐能力状态交付，中断时保存草稿和产物 |

角色消息按顺序交接。Builder 交验时等待 Validator；业务范围和研究依据疑问交给 Planner，接口、字段和实现问题交给 Builder。代码、文档、宿主固定验收条件或业务目标改变时更新验收版本；补充 implementation 与证据引用保留已有验收版本。

Planner 每项能力交付 `id`、`purpose`、`evidence_ids`，可附 `acceptance`、`implementation` 与 `depends_on`；全局 `limitations` 记录限制。校验目标、证据引用与依赖自洽。实际 API 参数和响应样本保存在研究中，Builder 自主决定交付接口。

Builder 将调用方式、参数、输出位置与含义、真实示例写入 `SKILL.md`，通过 `send_message(role="validator", content="请验收当前候选")` 交验。消息仅交接候选，框架不从消息中登记执行声明。Validator 阅读文档，自主选择包内脚本、普通选项、位置参数或 stdin。每项计划能力至少独立执行一次正常业务 CLI，以 `capability_id` 关联业务目标。`exec.output` 为空时读取 stdout，否则读取工作目录内相对路径的 JSON 文件；框架检查文件由本次执行更新。

业务验收调用统一由 Validator 发起。框架预检包结构，运行器限制脚本位于技能包内，同次执行检查退出状态、完整输出和 JSON 可解析。Validator 同时读取原始需求、业务计划、研究依据与文档，检查实际数据、作者、完整正文、来源 URL 与内容的对应关系及参数效果。缺少执行或语义结论的能力保留未完成状态；仅 JSON 可解析无法支持完整通过。

调用方显式提供的 `validation_examples` 保留固定约束，作为 `host_examples` 交给 Validator；机器检查继续使用其中的结果路径、必需字段和来源路径，Builder 消息不会改写它们。低层 `validate_examples()` 保留给单独包校验调用方。普通生成任务不要求 `records_key`、`source_key` 或 `required_fields`。

验收以声明范围内的正常输入为门禁：CLI 可用、JSON 可解析、参数生效、数据真实、字段与来源符合需求。非法输入、无匹配及其他边界按需探索，`boundary`、`empty` 和 `invalid_input` 调用仅作辅助观察。普通非法输入的空结果或失败、错误标签与退出码形式差异、未约定的顺序差异和探索边界问题写入逐能力 `warnings`，通过能力可保留这些提示。边界观察发现核心数据问题时，Validator 使用正常输入独立运行 CLI，再根据该调用判断失败。

完整输出、实际参数、执行编号和候选版本持久保存。Validator 可直接解析输出、对比分页、核对字段和来源；宿主固定样例仍提供 `record_summary` 与 `parameter_comparisons` 辅助信息。

## 状态由谁持有

| 对象 | 生命周期与状态 | 调用方式 |
| --- | --- | --- |
| `AccessPipeline` | 一次构建；角色引用、消息、checkpoint、Builder 预算 | `send_message()`、`validate()`、`context_snapshot()` |
| `PackageFiles` | 一次构建；候选目录、已登记文件、允许读取的结果路径 | `pipeline.package.read_file/write_file/edit_file()`、`snapshot()` |
| `ExecutionTools` | 一次构建；当前验收工作目录、候选版本检查 | `pipeline.executor.execute()`、`validation_work()` |
| `ValidationProgress` | 跨验收轮次；契约、函数索引、复验范围、上次报告、次数 | `begin()`、`prepare_review()`、`checkpoint_validation_progress()`、`end()` |
| `ValidationReview` | 一次固定候选验收；观察、用例、语义结论、正常业务失败队列 | `start()`、`observe()`、`submit()`、`result()` |
| Agent 与 `session.py` | 各自的 LLM 会话、调用统计、压缩与收尾 | 通过 `context_snapshot(role)` 获取进度摘要 |
| `BuildRecord` / `ToolResultStore` | 一次构建的持久记录与完整输出 | 写日志、保存结果、返回有界回执和分页位置 |

`prepare_review()` 返回独立输入副本；Validator 通过 `snapshot()` 提供恢复副本，通过回调报告进度。主流程根据这些交接数据恢复或合并结果。文件工具负责文件与路径安全，验收状态集中由 validation 模块管理。

## 增量验收与修复

1. 扫描包内 Python 函数，把函数正文、指纹、相对路径和字符读取位置存入函数索引。独立 CLI 的同一次执行记录实际调用函数，再结合包内函数引用确定能力范围。
2. 未通过、原正常业务失败输入未补验、函数内容变化、共享内容变化或契约变化时，相关能力进入本轮。通过且未变的能力复用原执行身份和结论；辅助观察与 warnings 保留，不触发强制复验。
3. 修复反馈包含 `package_files`、`next_actions[].functions` 和可直接调用的 `read_file` 参数。Builder 先读定位到的函数，再局部编辑；读取失败时使用恢复回执重新定位。
4. 原正常业务失败保留输入、原因与执行引用。接口或输出位置改变时，Validator 按新文档构造等价调用，并用 `exec.regression_of` 引用原失败执行 ID；执行通过并在语义结论中确认覆盖原问题后解除待补验项。修改文档或更换查询保留原失败义务。历史边界观察继续作为提示。
   原输入经来源确认应归类为无匹配或非法输入时，Validator 使用 `regression_of`、`check_kind=boundary` 与实际 `expected_status` 复验，并在结论中记录分类依据。该能力仍需正常业务调用通过，所有修订与实际执行保留在报告中。
5. Validator 指定下一阶段 1–50 次 Builder 修复调用；同一报告保留原额度。静态拒收或旧报告缺预算时后备为 50。初验之后最多三次修复交验，次数和草稿一起保存。

包内函数管理网络客户端、代理选项、超时与重试。Playwright 连接宿主托管浏览器，当前开启用户交互时显示窗口，关闭时使用无头模式。执行输出持续落盘，Agent 收到有界回执，再通过返回的路径和 `next_offset` 按需读取。

三个角色共用的浏览器指引要求在业务操作中适度移动鼠标、按内容分段滚动，并检查目标是否出现。Builder 将所选动作写入技能脚本或包内 helper，使用原生 Playwright，动作与业务步骤顺序执行并共用30秒预算；用户接管登录或验证时停止动作。该约定作用于后续探测、创建和修订，已有技能保持原脚本行为。

## 调试与验证

构建记录目录包含 `events.jsonl`、`builder.json`、`site-session.json`、`validation-<id>.json`、`tool-results/`，以及草稿和 `artifact/`。函数索引由验收回执给出路径。验收产生的工作文件在本次构建中继续可读，交验结束后 Builder 可读取失败产物。

Access 角色契约版本为 3，写入新草稿的 `contract_version` 和站点会话的 `version`。版本 1、2 的草稿与报告保留读取，旧契约的续建和补验入口提示重新创建任务；新版本继续支持草稿恢复。已安装技能与浏览器登录状态沿用现有运行机制。

```bash
python -m pytest tests/test_access_*.py tests/test_site_planner_*.py -q
python -m pytest tests/test_skill_*.py tests/test_portable_skill_*.py tests/test_trace_skill_updates.py tests/test_web_skill_creation.py -q
python -m searchos.skills.pipeline.access.pipeline --help
```

对外调用继续使用 `searchos.skills` 或外层 `pipeline.run.run_pipeline()`；需要单独构建 Access 时导入 `access.pipeline.build_skill`。旧内部路径已迁移，调用方应更新 import。

| 原位置 | 现位置 |
| --- | --- |
| `run.py`、`delivery.py`、`workspace.py` 的编排 | `pipeline.py` |
| `workspace.py` 的文件、执行、验收状态 | `tools/files.py`、`tools/execute.py`、`validation/progress.py` |
| `planner/agent.py`、`planner/contract.py` | `agents/planner.py` |
| `builder/agent.py`、`validator/agent.py` | `agents/builder.py`、`agents/validator.py` |
| 三角色的 `prompt.py` | `agents/prompts/*.py` |
| `browser.py`、两角色的 `tools.py`、`execution.py` | `tools/web.py`、`tools/execute.py` |
| `function_index.py`、`validator/regressions.py`、验收会话状态 | `validation/progress.py` |
| `validator/checks.py` | `validation/checks.py` |
| `context.py`、`control.py` | `session.py` |
| `records.py`、`results.py`、`text_files.py` | `artifacts.py` |
