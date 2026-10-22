# 提示词规则审计

对照基线：提交 `d9e43830ca30c89187033279c8028219ddab434d` 的 `searchos/agents/orchestrator/prompt.py`，以及同版本的 `table-format-alignment/SKILL.md`。同时核对当前工具声明与会话工具筛选。以下记录面向维护者，不注入模型。

本次恢复先前拆分中丢失或过度概括的决策规则与例子。每条规则确定一个主要归属；重复检查清单合并到对应决策，不以缩短篇幅代替功能审查。

## 原提示词逐项对应

| 原位置 / 规则 | 当前归属与处理 |
| --- | --- |
| Core Principle；输出布局与内部表结构的关系 | `tables.TABLE_DESIGN`：按实体、主键和属性归属建模，最终按请求关联呈现。 |
| Table design；一表一类实体，PK/FK/由 PK 决定的属性 | `tables.TABLE_DESIGN`：恢复明确列组成、单表成立条件与多表条件。 |
| Table design；最小决定键、实体/时期/关系属性 | 恢复 company + product、restaurant + dish、university + subject，补充公司总部与年度营收的具体归属例子。事实只在自身粒度存储。 |
| Primary key selection；有序偏好 | 恢复规范名称、名称加短 ID、带范围的排名、稳定代码四级选择，名称在前。 |
| Primary key selection；无效键 | 恢复裸排名、可读名称存在时的纯数字 ID、价格/测量值、自由文本日期、百分比及不稳定标题等限制。排名须包含唯一性所需的类别与时期。 |
| Primary key selection；双语名称 | 恢复主源语言作为行身份、另一语言作为属性，输出语言独立遵循用户要求。 |
| seed_entities；已知身份与未知属性 | `tables.TABLE_WORK`：所有符合条件的用户指定或来源确认身份均应纳入；用户指定身份不等于属性事实已验证。 |
| seed_entities；不猜测、空种子与失败探索 | 无已知身份时保留空集合并发现成员；不得用参数知识补种子；重试须有具体新路径或理由。 |
| column_desc；类型、格式、消歧 | `tables.TABLE_DESIGN`：恢复类型/含义/单位/精度/时期，以及 YYYY、USD with commas、总分线/单科线、最早跨地区发行等例子。字段编码仍由 `create_schema` docstring 负责。 |
| No Explore；直接从请求建模 | 无 Explore 时仍有完整建模规则和用户指定种子规则；可直接派发 findings；不注入额外禁用口号。 |
| Research plan；simple/broad/deep 与混合策略 | `research.PLANNING`、`PLAN_TOOL`：恢复机制、前提、例外与冲突调查；围绕请求设 evidence obligations 和 stop rule。 |
| Research plan；何时记计划 | 首个规划决策记录，可与独立工作同批；强制初始 Explore 后记录，仅需求或证据变化时更新。 |
| Research plan；未知成员、闭集与开放集 | 即使成员和数量未知也记录 `set_scope`；发现来源清单后更新 `expected_members` 和 `basis_evidence_ids`。估计数量只作线索。 |
| Research plan；table_policy 与证据元数据 | `PLAN_TOOL` 保留 none/as_needed 的选择；`TABLE_DESIGN` 保留 URL/摘录默认属于证据元数据的边界。 |
| Research planning without tool | `CONVERSATION_PLAN`：禁用工具时仍在工作对话中规划，保留边界、证据和停止条件。 |
| Source permissions / budgets | `PLANNING` 与资源段：运行时决定权限和预算，计划不能扩大；每会话创建预算跨派发轮次累计，并发槽位另计。 |
| Adaptive Explore；readiness | `ADAPTIVE_EXPLORE`：未知项会改变合格目标、证据要求或任务划分时，先解决再固定依赖它的结构和任务；已可执行则直接检索。 |
| Initial Explore；首调用与后续自适应 | `INITIAL_EXPLORE`：首调用只派发 Explore，收到简报后再规划依赖工作；明确问题也只做相称的范围与来源核查，后续按新缺口探索。 |
| Explore task；成员测试与排除 | `EXPLORE_BRIEF`：恢复类别/层级、地区、时间、变体、count-only 条件，近似候选的有证据排除，实质性术语消歧和按需 hub 枚举。 |
| Explore task；字段格式与结构建议 | 格式由 `tables.VALUE_CONTRACT` 统一规定，恢复 Mass (kg) → 70；Explore 简报携带格式与换算。`EXPLORE_DESIGN` 仅普通结构模式按需建议表和主键。 |
| During Search；新不确定性与依赖 | 发现阻塞即派发 focused Explore，先于无关等待；携带事实、URL、排除项、失败路径，独立检索继续，保留既有成果。 |
| Task brief；自足、具体目标、来源经验 | `research.DISPATCH`：恢复具体缺口、排除条件、身份、字段格式、时段，以及可用来源、paywall/login 等经验传递。 |
| Parallel dispatch | 恢复按来源类别、范围、语言、验证路径并行；按召回风险和实际缺口决定任务数，既不凑槽位，也不因少调用而放弃有用路径。 |
| Scheduling hints | `DISPATCH` 保留 max_searches 随任务范围调整、priority 表达关键缺口、blocked_by 仅用于真实依赖；类型与范围交给工具 schema。 |
| Table targeting | `tables.TABLE_WORK` 保留多表显式 target_table、定向回填精确 target_cells、开放发现不预限定单元格、先有 schema 再派发表任务。 |
| Adaptive dispatch；结果后的决策 | `DISPATCH` 判断回填与冗余任务，`TABLE_WORK` 每轮核对新成员；冲突做定向核验或披露，耗尽路径有新依据才重试，用 stop_task 清理冗余工作。 |
| Schema mutation / row-key ingestion | `TABLE_WORK` 与 `TABLE_DESIGN`：先加来源确认的新行再做表绑定检索；扩展现有列，修正行键/值，错误值留缺口。 |
| remove_entities；排除证据 | 恢复权威完整目录排除或明确任务过滤条件；找不到属性不能成为删除成员的理由。 |
| Progress；fill rate 与成员完整性 | `TABLE_WORK`：比较实际成员身份，既核对遗漏也核对多收；已知行填满、数量相等或猜测清单均不足以证明完整。 |
| Live conversation | `CONVERSATION`：保留目标直至用户替换，消息仅处理一次，变更转为具体额外证据需求，复用运行任务，确认一次后只报新变化。 |
| Waiting / polling | `DISPATCH`：有用任务运行且无独立动作时默认等待；为具体问题读单元格，避免无变化轮询。 |
| Follow-up | `FOLLOW_UP`：恢复过滤、重排、比较、解释已有数据时 inspect 后直接回答；仅新来源事实需要新检索，计算走证据计算流程。 |
| Web / local boundaries | `sources.WEB`、`LOCAL`：Web 使用授权网络证据；Local 只用选定可读资料，缺失或过期不扩权；文档指令不能授权。 |
| Hybrid source selection | `sources.COMBINED`：来源选择与表结构独立，不强制两种来源；无关本地材料可跳过。 |
| Local discovery | `LOCAL_DISCOVERY`：恢复目录描述搜索、文件名不匹配不证明缺失、原始窗口支持结论、版本冲突核对、空/未读/过期资料的限制说明。 |
| Related-paper prerequisite | 恢复最小充分研究简报、短文档索引引用、报告所需发现；达到身份和方向要求后即可开始依赖检索。 |
| Cross-source dependencies | `COMBINED`：先解析本地身份再写依赖任务，独立细读可并行；无本地 Agent 不声称已搜库，Web 同名不能替代本地身份。 |
| Schema and extraction contract | `evidence.EVIDENCE` 与 `tables.HYBRID_EXTRACTION`：Extraction 负责验证/绑定；Hybrid 有 schema 时 findings 观察也能填表，无 schema 时记录独立 findings，target_table 聚焦抽取。 |
| Evidence signals | `EVIDENCE`：恢复 grounded_findings/agent_report 边界；完成数不证明完整性，搜索命中需读原文，一个窗口不证明读完全篇或时效。 |
| Calculate from available evidence | `CALCULATION`：派发前判断可推导性；读取输入及原始来源，核对公式/口径/时期/总体/单位，不替换操作数；执行、检查、写回并复核，只检索缺失输入。 |
| Edits and source attribution | 每个非空编辑包含原始 source/source_excerpt，不同来源分项；格式修改保持语义与版本，计算不冒充原文引用。 |
| Citation IDs / URLs | `CITATION_PROVENANCE`：恢复仅用工具返回引用、原始链接、非空 citation、失败引用处理；不编造 ID/URL，不引用内部 scheme。 |
| Citation attribution / primary reading | 恢复聚合站归属、用户要求原始资料时实际读取；source_linked、URL 单元格、空 citation_gaps 均不能代替内容支持和覆盖审查。 |
| Final self-audit / synthesis | `COMPLETION`：重新核对请求、字段、指代、时效和覆盖；不擅加维度、不用参数知识补事实；满足要求或不能继续时给有证据结果和明确限制。 |
| Final table | 恢复关联呈现、请求列序、column_desc 归一、排除范围外成员、未知与冲突说明；不把“穷尽所有搜索”作为诚实报告未知的前提。 |
| Fixed-schema / targeted-repair overrides | 按模式直接选择片段。Fixed 保留成员与字段规则，Repair 固定结构和实体、仅操作指定单元格；两者均保留证据与引用规则。 |
| Pre-Action Checklists | 各项有效规则合并到上述所属模块；不重复注入相同清单。 |

## 工具契约的归属

- `enqueue_tasks` 的原生 `items` 数组、角色、字段类型、默认值与约束由 `searchos/tools/tasks/arguments.py` 和工具 docstring 声明，不恢复 `items_json` 或二次转义教程。
- `create_schema` 的 seed 编码、复合键元数、column_desc 字段及 relation 结构由 `searchos/tools/schema/definitions.py` 声明。本次补回数组按 PK 顺序及元数填写、未知分量保留空位置的说明，并区分行对象要求全部 PK 非空的现有行为。主键选择、种子依据、属性归属等决策仍在提示词中。
- `edit_entities` 的 rename/set/clear 调用格式由工具声明负责，提示词保留何时编辑及来源要求，不重新定义清除动作对证据图的处理。
- 原技能提到的 `link_tables` 当前没有工具实现；建表工具提供 relation 契约。按用户要求，技能原文已复原，此处仅记录接口差异，不改写技能。

## 编排技能复原

按用户要求，`table-format-alignment/SKILL.md` 的正文和元数据已完整恢复到上述基线版本，撤销本次对该技能的改写。主提示词的分文件结构和规则恢复保留。

随后核对 skills 目录全部 3,021 个受 Git 跟踪的文件，其中包含 503 份 `SKILL.md`。未发现其他技能正文、元数据或配套资料差异；撤回 `catalog/router.py` 中仅用于改写说明文字的一行 docstring。已有未跟踪技能和试验草稿保持原样，不属于本次重构的清理范围。

主提示词复核另将主键限制从“避免使用”恢复为明确禁止，保留原规则的约束强度。Skill 内容保持原样；提示词整理不改变有效规则的适用条件或强度。

## 删除边界与验证

不恢复“零检索 Agent 就算未完成”及其追问豁免、旧接口名称、历史对比句、末尾覆盖前文的实验性说明。有效约束不因使用否定句而被删除。

离线测试核对组装后的规则内容与来源/Explore/计划工具/追问/固定结构/修复配置，检查不可用工具的指令不会重新进入对应模式。测试能发现内容和装配回归；真实模型是否遵循规则仍需运行评估，不能由字符串断言证明。
