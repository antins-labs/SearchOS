---
name: ranking_top_n
description: 排行榜/Top-N 类查询的两步策略：先锁定权威排行，再逐条补充属性
trigger: 查询含 Top N、排行榜、最快/最大/最高等排序类问题
success_rate: 0.0
status: seed
trigger_conditions:
  domain:
  - general
  entity_types:
  - entity
  attribute_types:
  - ranking_metric
cost_hint: mid
effectiveness_score: 0.0
---

# Skill: Ranking Top-N（排行榜两步锁定策略）

## 目标
解决"既要排名列表，又要每条目附加属性"的高频题型。
排行榜本身可能随时间变动（市值、票房、圈速），每条目还需额外字段（CEO年薪、轴距、导演国籍）。
核心策略：**先锁榜 -> 再补字段**，两步闭环，防止排名漂移或字段缺失导致答案自相矛盾。

## 适用场景
题目同时满足以下条件：
1. 明确或隐含"截至某时刻"的时间点
2. 要求"前N按某指标排序"
3. 还要"每条目的另一属性"

典型问法：
- 截至2024年底，全球市值前3的科技公司及其CEO年薪
- 纽北圈速最快5辆量产街车及各自轴距（英寸）
- Steam周销量榜前5游戏及首发价格
- 截至上月，国内票房前5影片及导演国籍

## 不适用场景
- 排名完全静态（如"历届奥斯卡最佳影片"），直接用列表检索
- 只需属性、无需排名（如"苹果CEO历年薪酬"）
- 开放性总结（如"2024年AI行业趋势"）

## 核心原则

### 原则1：先锁榜，再补字段
绝不"边查边拼"。必须先拿到**同一信源、同一时刻**的完整 Top-N 名单，再逐条补属性。
防止"第2名"在两次查询间移位。

### 原则2：权威源优先
始终从**官方或经过验证的权威源**开始：
- 财务排名：Bloomberg、SEC 文件、交易所公告
- 竞技/性能：官方数据库（如 nurburgring.de）、Wikipedia 结构化表格
- 文娱榜单：Box Office Mojo、Billboard、SteamDB
严禁从第三方博客/媒体"Top 10"文章锁榜。

### 原则3：双重验证边界位次
对第N名与第N+1名的边界位次必须**二次查询确认**，防止快照差异导致名次颠倒。

### 原则4：定义严格匹配
题目限定"量产/合法上路"等条件时，锁榜时必须确认榜单来源是否严格执行了该定义。
否则后续补字段全是错的。

## 执行流程

### Step 1：一次性拉取完整榜单
1. 构造"截至 + 时刻 + 领域 + Top-N + 排序指标"查询
2. 优先选同一权威源（如 Wikipedia 结构化表格、官方 PDF）
3. 记录：名次、主键（公司/影片/车型）、指标值、数据来源 URL、快照时间

**查询模板**：
- 中文：`截至{YYYY-MM-DD} {领域} 前{N} {排序指标} 排名 site:{权威域}`
- 英文：`Top {N} {superlative} {entities} {context} site:{authority}`

### Step 2：边界位次二次验证
若题面已暗示争议或相邻位次指标值接近（差距 <1%），单独搜索对比确认。
对比两次快照，若名次一致则锁定；不一致则以最新一次为准并留痕。

### Step 3：生成"补字段"待办清单
对锁定后的 Top-N，逐条列出待补属性：
- 用英文主键 + 年份 + 属性关键词构造查询，避免中文译名歧义
- 例：`Tim Cook "2024 total compensation" Apple SEC filing`

### Step 4：逐条补字段并交叉验证
1. 优先用一级披露源（SEC 10-K/DEF 14A、制造商技术规格 PDF、官方票房公告）
2. 若出现区间值或不同口径，取同一口径并备注
3. 对精确数值（如轴距），从制造商官方 PDF 提取公制值后换算

### Step 5：闭环回写
1. 逐条标记"排名 + 属性"均完成
2. 若某字段缺失，显式声明"未披露"而非留空


- **场景**: 当需要为排行榜中的多个实体（如Top-5×5学科=25所大学）补充同一类属性（如申请截止日期、申请费）时
  - ❌ 踩坑: 对每个实体并行派发独立agent执行相同的属性查询任务，导致buffer溢出和dispatch预算耗尽
  - 原因: 同质化查询（相同属性类型、相似搜索路径）的大规模并行会触发系统资源竞争；且当某一属性查询受阻时，所有并行agent都会陷入相似的死胡同，无法互相借力
  - ✅ 应改用: 采用分批串行或属性优先策略：1) 先完成一批实体（如5所）的所有属性收集，再处理下一批；2) 或按属性分阶段——先集中收集所有实体的'申请截止日期'，再收集'申请费'；3) 设置并行上限（如同时最多3个同质agent），避免资源风暴
  - _来源 trace: My son is about to start his university applications in 2025 for postgraduates but he’s still uncert_ _(2026-04-23)_

- **场景**: When a ranking query requires extracting Top-N entities across multiple categories (e.g., 5 subjects × 5 universities = 25 entities), and each entity needs multiple attributes from diverse sources (rankings from 3 systems, application deadlines, fees from official sites)
  - ❌ 踩坑: Dispatching many parallel agents (10+ simultaneous agents) to gather all entity attributes at once, rather than following the prescribed sequential '先锁定权威排行，再逐条补充属性' approach
  - 原因: Over-parallelization exhausts dispatch budget (dispatch_budget_exhausted_x3) and fills evidence buffers (buffer_full), causing the system to stall and drop partially collected data. The agent also got stuck in search loops (NO_PROGRESS, SEARCH_LOOP) during the explore phase, wasting steps.
  - ✅ 应改用: Follow strict hierarchical decomposition: 1) First complete the ranking extraction for ALL entities from authoritative sources before moving to attribute gathering; 2) Process attribute collection in controlled batches (e.g., 3-5 entities at a time) rather than all 25 simultaneously; 3) Prioritize high-value attributes (rankings) before low-value/variable ones (application fees which vary by program)
  - _来源 trace: My son is about to start his university applications in 2025 for postgraduates but he’s still uncert_ _(2026-04-23)_

