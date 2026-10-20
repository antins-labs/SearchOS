# SearchOS

SearchOS 由 Orchestrator 调度 Agent 与 Access Skill，把带来源的事实写入 Evidence Graph，并按需通过 Coverage Map 组织表格。研究进展同时来自阅读、有效事实、任务证据关联和表格更新。

## Language

**Access Skill**：针对特定来源或检索方法、向 Agent 返回结构化结果的可执行检索能力。
_Avoid_：插件、爬虫脚本

**Executor**：Access Skill 目录中实现 `execute(params, ctx)` 契约的 Python 文件。
_Avoid_：任意脚本、内嵌工具

**Skill Execution**：依据一份 Execution Policy，在隔离 worker 中完成的一次 Executor 调用。
_Avoid_：动态导入、受控环境

**Execution Policy**：一次 Skill Execution 被明确授予的网络、文件、资源与输出权限集合。
_Avoid_：沙箱配置、隐式权限

**Browser Automation**：Executor 在 Skill Execution 内自行启动和管理的 Playwright driver 能力；它不是通用子进程权限。
_Avoid_：shell 权限、任意命令权限

**Need Intent**：由用户信息需求产生、可能对应零到多个 Strategy Skill 或 Access Skill 的创建意图。
_Avoid_：任务类型、单 Skill 请求

**Source Intent**：针对一个已观察来源、通常对应一个 Access Skill 的创建意图。
_Avoid_：host 配置、抓取任务

**Repair Intent**：从失败轨迹产生、可能对应零到多个 Strategy Skill 或 Access Skill 的创建意图。
_Avoid_：重试请求、错误标签

**Creation Pipeline**：接收一种已成立的 Intent，并使用具体创建 Implementation 产出 Skill 创建结果的 Module。
_Avoid_：Evolution 生命周期、发布工作流

**Skill Availability**：表示一个 Skill 是否允许进入运行时注册、选择和执行的二元属性；只取 enabled 或 disabled。
_Avoid_：mined/seed/trial/active/optimized 生命周期

**Evidence Observation**：来自页面、Access Skill 或 Agent Summary，等待抽取与验证的一份来源观测。
_Avoid_：原始工具结果、待写节点

**Evidence Extraction**：将 Evidence Observation 经过切片、Judge、Grounding、去重和原子提交转化为 Evidence Graph 与 Coverage Map 更新的生命周期。
_Avoid_：Evidence Middleware、抽取回调

**Source Observation**：findings 与 Hybrid 表格事实所依赖的持久化原始阅读窗口，包含来源、正文、哈希及本地定位元数据；窗口内字符偏移不代表原文件页内坐标。

**Task Evidence Binding**：一个 Frontier Task 与一条有效 Evidence 的用途关联，关系为 supports、contradicts 或 context；不改变事实身份或任务执行状态。

**Cell Evidence Binding**：一个单元格对已有 Evidence 的投影，包含目标格的值、alignment 与用途状态；同一事实可支撑多个格，清空某格不撤回其他用途。

## Relationships

- 知识库文件只保存一份原文与解析产物，可关联多个主题。目录短引用名用于 Markdown 链接和卡片显示，原始文件名保留用于详情与下载。
- 主题 ID 不随 Recap 生成改变。上传依据文件 Recap 自动归类；手动调整归属后，自动更新只刷新文件信息，不覆盖用户选定的关系（包括取消全部归属）。
- 主题成员或文件 Recap 改变后标记摘要待更新，后台使用当前成员的文件 Recap 生成主题摘要。发布前校验成员与内容指纹，过期结果不发布；失败保留旧摘要并允许重试，重启后继续待更新任务。

- 一个 **Access Skill** 恰好包含一个 **Executor**
- 每次 **Skill Execution** 恰好运行一个 **Executor**
- 每次 **Skill Execution** 恰好受一份 **Execution Policy** 约束
- 所有 **Access Skill** 使用同一 Skill Execution 接口和 Execution Policy
- **Access Skill** 可使用受识别的 **Browser Automation**，但不可启动其他子进程
- **Browser Automation** 不做主机过滤；Executor 负责完整管理 browser / context / page 生命周期与所需会话状态
- Dynamic Builder 的构建产物只有通过隔离 smoke test 后才能安装为 **Access Skill**
- **Need Intent** 与 **Repair Intent** 均可对应零到多个 Skill 创建结果
- **Source Intent** 通常对应一个 Access Skill，但 hostname 不是全局唯一 Skill 标识
- **Creation Pipeline** 不负责运行时 Skill Selection，也不反查创建关系决定注入
- 开启运行后生成技能时，每轮搜索固定本轮轨迹，独立记录后台生成进度和结果。WebUI 会话按轮次显示新增、更新与未入库状态；只有校验入库成功的结果计入变化，历史预览读取当轮保存的技能正文，不随技能库后续更新改变。
- 只有 **Skill Availability** 为 enabled 的 Skill 才会进入运行时 registry；旧 lifecycle 值仅在读取时兼容映射
- 每个 **Evidence Observation** 只能在一次 **Evidence Extraction** 生命周期中被预留一次
- 模型可见的工具结果只保留事实、来源、操作标识及影响下一步决策的状态；哈希、内部路径、性能时间和完整审计元数据保留在状态、日志或工具 artifact 中。来源版本引用、观测 ID、representation 与阅读位置仍可用于后续操作，不能按字段名称一概删除。原文与技能返回的业务 JSON 保持完整，不递归剥离其中的 `meta` 或 `sha` 字段。
- Evidence 的 `source` 保留观测身份，`source_urls` 保存该条事实引用的原文地址。Access Skill 从返回结果的来源字段传递链接，Agent Summary 从逐条引用传递；抽取只能选择观测已声明的地址。多来源结果按事实归属，未知来源不猜测。回答、证据面板与表格引用解析到原文，内部执行地址保留用于审计；链接可追溯不等于原文已支持该陈述。
- `edit_entities` 在所有来源模式下写入非空事实值时，必须提供原始 http/https/local 地址和支持摘录；skill/agent 事实先读取 `source_urls`。纯重命名和清空不要求来源。此检查阻止无来源覆盖，不替代语义核验。
- 一次 **Evidence Extraction** 提交必须让 Evidence Graph 与 Coverage Map 的更新原子可见
- 自动抽取与手工断言共用证据提交规则；单元格只引用实际持久化且归属匹配的证据
- 行排除表示当前答案范围变化，不改变证据事实状态；自动抽取不能恢复已排除行
- Coverage、报告与评测导出共用证据优先级；默认回答视图排除失效证据与范围外行
- 无表 findings 经摘录定位和支持核验后提交；Agent Summary 是否进入抽取由 FinalSummaryEvidenceMiddleware 的装载决定，核心不按来源模式禁用摘要
- Hybrid 已有 schema 时，Evidence Extraction 按 schema 抽取事实并自动投影到单元格，任务的 findings 标记不跳过此步骤；显式 target_table 优先，未指定时检查已声明的各表。抽取仍自动关联原任务，无 schema 时保留独立 findings
- Hybrid 建表和行编辑只管理结构，事实值由原文 Extraction 或已有事实投影支持；摘要抽取使用独立 middleware，来源标识保留为 `agent://`
- 一条 Evidence 可以关联多个 Frontier Task，同一 Source Observation 可以支撑多条事实；事实、原始窗口与新增任务关联在同一次状态更新中持久化
- 检索执行报告保存派发时的任务 ID，任务回收或改派不改变报告的证据归属。循环停止且已有有效任务证据时取消原任务的自动重试，由 Orchestrator 核对已有事实并仅派发具体剩余缺口；取消不代表研究完成。
- 新任务可按原字符窗口重新抽取已保存的 Source Observation；复用经过范围、哈希与支持核验，不代表全文已读或来源版本已更新
- 已有事实经过来源支持核验后可生成多个 Cell Evidence Binding；读取和导出按目标格取投影值，保留原始事实与来源。Hybrid 自动 table Extraction 写入独立事实与投影，历史节点及普通 Web 表格写入继续兼容
- Hybrid 的本地范围由显式 library 或 documents 选择确定；library 固定当前库提交时的可读文档快照，允许目录探索，不授权其他库。来源决策与是否建表相互独立，未提供 local 范围不隐式扩大权限。
- 来源模式由用户选择：Web 仅联网，Local 直接读取所选本地范围，只有 Hybrid 允许 Orchestrator 调度两类检索 Agent
- 普通运行中，Orchestrator 按具体不确定性决定是否调用 Explore；明确的多实体、多属性任务可直接建表并检索。评测通过任务级配置默认先 Explore，再按简报检索；显式关闭 Explore 的消融设置优先。Search 中出现新的身份、范围或候选缺口时，可继续调用 Explore，保留既有表格与证据，独立任务继续运行。
- **ResearchPlan** 由现有 Orchestrator 保存可组合的 simple/broad/deep 策略、证据义务、建表选择、集合边界和停止条件，不增加分类模型调用，也不改变来源权限与预算。没有显式表目标的任务在计划无需建表或尚无表时默认 findings；显式表任务保持原约束。SOCM 注入计划及缺失/多余成员，coverage 仍只计算已知行填充。成员依据标为 source_linked 只表示引用有效；估计数量、相等数量和开集检索均不能证明完整召回。
- Explore 没有会话创建次数上限和最少探索轮次；目标解决即可结束。单次批量探索受波次上限约束，所有探索仍受并发与通用预算约束，产品与评测采用同一停止规则。

- 实时追问由同一 Orchestrator 图在模型边界消费，每条消息独立标识并仅注入一次。立即引导可撤销尚未完成的模型生成或唤醒 `check_agents`；工具返回后加入模式等待当前工具批次的完整结果。两种模式均保留已派发子任务，普通工具不因追问取消。Web 默认排队并在输入框上方显示待处理消息；“引导”就地提升为立即投递，“删除”撤回尚未消费的消息，已消费消息不可重发或撤回。TUI 普通输入立即引导、`/after` 延后加入。
- 工具生命周期由统一执行层记录，调用开始即可推送 UI，结果、失败和取消按调用 ID 更新原卡片。对话在追问实际注入的位置分段，后续工具进入新的调用块；模型中间回复不表示研究完成，完成标记由运行结束事件决定。
- 追问默认调整当前目标，不重复启动研究；进展文字只说明新发现、决策和障碍。空闲并发槽不构成扩展范围的理由，综述不隐式变成逐年穷举。预算停止后的最终生成保留已收到的追问及其顺序。
- 工具额度耗尽不删除模型工具目录；Budget Middleware 在执行前拦截超额调用，并以回执和连续拒绝上限引导收尾，避免网关的未注册工具错误绕过控制层。
- Evidence Extraction 收尾先完成观测提交，再用剩余时间核验冲突；核验超时保留 `pending` 状态和已提交证据，不触发整个检索任务重跑。真正的抽取失败与外部取消仍向上传播，Agent 卡片显示失败原因及任务回收状态。

## Example dialogue

> **开发者：** “Dynamic Builder 已经生成 Executor，可以直接导入验证吗？”
> **领域专家：** “不能。它必须通过 Skill Execution 在独立 worker 中验证；主进程永远不导入 Executor。”

## Flagged ambiguities

- “受控环境”过去既表示普通 `asyncio.wait_for`，也暗示安全隔离；现统一为 **Skill Execution**，且必须有显式 **Execution Policy**。

## 运行性能约束

SOCM 使用按文件版本失效的不可变字节快照；每次解码返回独立状态对象，事务内读取、文件锁和原子发布仍是并发写入边界。实时同步使用完整基线与版本化增量，必须表达证据撤销和单元格删除。对话采用完整追加日志与周期快照，读取经统一回放入口，不以删减阅读历史换取性能。独立 Recap 批次可有限并发，输出保持原文顺序。实现、基准和验证见 [运行性能](docs/development/runtime_performance.md)。
