---
name: temporal_offset_reasoning
description: 解决需要基于已知锚点事件进行时间运算（加减法）以定位目标事件的问题。强制执行"锚点定位-数值计算-目标检索"的分步策略。
trigger: 查询含"X年前/后"、"exactly N years before/after"等相对时间偏移，或需要区分过去/现在/未来时态
success_rate: 0.0
status: seed
trigger_conditions:
  domain:
  - general
  entity_types:
  - event
  - entity
  attribute_types:
  - date
  - age
  - duration
  coverage_gap_pattern: temporal_math
cost_hint: mid
effectiveness_score: 0.0
---

# 时间偏移推理技能

## 目标
解决包含相对时间偏移量或隐含时间推理的查询问题。此类问题无法通过单次搜索直接找到答案，因为目标事件的时间点依赖于另一个已知事件（锚点）的时间戳加上/减去一个时间差。本技能将复杂的时间推理链分解为可执行的搜索步骤。

## 适用场景
- **相对时间查询**: 问题中包含 "X年前/后"、"Exactly X years before/after" 等字样
- **事件依赖关系**: 目标事件定义依赖于另一个更知名的事件（锚点）
- **时态推理**: 需要区分"当时的"、"现任/前任"、"过去/现在"等时态信息
- **时间可行性判断**: 目标事件可能尚未发生（未来事件），需要先验证时间可行性
- 示例:
  - "What painting was stolen from The Louvre exactly 56 years before the birth date of Serj Tankian?"
  - "Who won the Nobel Prize in Physics 10 years after the discovery of X-rays?"
  - "What league was Ilsinho's team in?"（需要判断 past vs present）

## 不适用场景
- 问题中直接给出了具体日期（如 "What happened on August 21, 1967?"）
- 时间描述模糊，无法进行精确算术运算（如 "Shortly after World War II"）
- 不涉及时间计算的单跳事实查询

## 核心原则
1. **锚点优先**: 必须先完整解析锚点事件的确切日期，再进行任何后续推理
2. **显式计算**: 不要让搜索引擎"理解"相对时间逻辑，Agent 自行完成算术运算
3. **解耦检索**: 将"找锚点日期"和"找目标事件"拆分为两个独立搜索
4. **时间可行性验证**: 在搜索前先判断目标事件是否已经发生。未来事件不可检索，应立即告知用户或转向历史趋势数据
5. **使用绝对时间**: 将相对时间描述（"大萧条期间"）映射到绝对年份范围（1929-1939），再构造查询
6. **粒度对齐**: 问题要求"日"就别停在"月"，要求"顺序"就列出全部候选再排序
7. **优先权威时间戳**: 政府/组织官网日程、官方新闻稿、PDF 议程、奖项公示页优先于新闻报道

## 标准执行流程

### 步骤 0: 时间可行性检查（前置）
- 判断目标事件是否在未来。如果是（如"ACL 2028 论文数"），立即返回"该事件尚未发生"
- 若涉及"当时的/前任的"表述，明确需要查找的是过去状态还是现在状态

### 步骤 1: 锚点事件识别与提取
- 分析问题，识别 `Anchor_Event`（锚点事件）、`Offset_Value`（偏移数值）、`Offset_Direction`（过去/未来）以及 `Target_Context`（目标事件背景）

### 步骤 2: 检索锚点日期
- 查询构造: `[Anchor Entity] [Event Type] date`
- 必须提取出 `YYYY-MM-DD` 或至少 `YYYY` 格式的日期

### 步骤 3: 执行时间算术
- `Target_Date = Anchor_Date + (Offset_Years × Direction_Sign)`

### 步骤 4: 检索目标事件
- 查询构造: `[Target Context] [Calculated_Date]`
- 此时查询词中不再包含相对时间描述，而是替换为计算出的绝对时间点

### 步骤 5: 交叉验证
- 用两个独立来源确认同一时间点，避免单源错误

## 检索策略模板
- 锚点日期: `"{Anchor_Entity} {Anchor_Event_Type} date"`
- 目标事件: `"{Target_Context} {Calculated_Date}"`
- 历史时期定位: `{period} {event/entity} site:wikipedia.org`
- 奖项/作品年份: `"YYYY" {award/work} winner`
- 精确日期（权威源）: `"{event name}" "{YYYY}" date site:domain.gov OR site:domain.edu`
- 顺序/排名: `"{entity}" "declare/establish/founded" "{YYYY}"` 然后按时间排序


## 示例

**问题**: "What painting was stolen from The Louvre exactly 56 years before the birth date of activist and songwriter Serj Tankian?"

**执行过程**:
1. **分解**: 锚点=Serj Tankian出生, 偏移=-56年, 目标=从卢浮宫被盗的画
2. **检索锚点**: `Serj Tankian birth date` → 1967-08-21
3. **计算**: 1967 - 56 = 1911, 目标日期=1911-08-21
4. **检索目标**: `Louvre painting stolen August 1911` → Mona Lisa
5. **结论**: The painting is the Mona Lisa.

1.  **分解问题**:
    - 锚点事件: Serj Tankian's birth.
    - 偏移量: 56 years before (-56 years).
    - 目标背景: Painting stolen from The Louvre.

2.  **步骤 1 - 检索锚点**:
    - Action: `search_agent` task="What is the exact birth date of activist and songwriter Serj Tankian?"
    - Search Query: `Serj Tankian birth date`
    - Result: Found evidence that Serj Tankian was born on **August 21, 1967**.

3.  **步骤 2 - 时间计算**:
    - Calculation: 1967 - 56 = 1911.
    - Target Date: **August 21, 1911**.

4.  **步骤 3 - 检索目标**:
    - Action: `search_agent` task="What painting was stolen from The Louvre exactly 56 years before the birth date" (Agent now knows the date context).
    - Search Query: `Louvre painting stolen August 1911` or `Mona Lisa stolen 1911`.
    - Result: Found evidence that the **Mona Lisa** was stolen on August 21, 1911.

5.  **结论**: The painting is the Mona Lisa.

