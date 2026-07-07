---
name: multi_hop_bridge
description: 通过“实体-属性-实体”链式检索，把分散在多处的信息桥接起来，回答需要 2 步以上推理的问题。
trigger: 当问题包含“谁/哪里的 X 与 Y 的关系是什么”或“先找 A，再基于 A 找 B”这类跨实体、跨文档的提问时启用。
success_rate: 0.0
status: seed
trigger_conditions:
  domain:
  - general
  entity_types:
  - entity
  attribute_types:
  - any
  coverage_gap_pattern: multi_hop_reasoning
cost_hint: high
effectiveness_score: 0.0
---

# multi_hop_bridge

## 目标
解决需要“先定位一个实体，再以该实体为跳板去定位第二个实体或属性”的多跳搜索问题。单条文档往往只包含部分线索，必须串联多条信息才能得出最终答案。

## 适用场景
- 例1：Where is the place **Norman Allen Adie moved to the US to work at** located in?  
- 例2：When did the **first casino open in the city where WPGG is licensed**?  
- 例3：Identify the **show that features the character Christian Mann**.  
- 例4：Find the **construction cost of Hvalbiartunnilin tunnel on Suðuroy, Faroe Islands**.  
- 例5：Which **white large hoofed mammal endemic to North America** does the Stoney word *waputik* refer to?

## 不适用场景
- 单跳即可完成的定义型问题（如“什么是光合作用？”）。  
- 需要主观判断或观点类问题（如“这部电影好不好看？”）。  
- 完全依赖实时数据且无法通过已知实体桥接的问题（如“现在比特币价格是多少？”）。

## 核心原则
1. **先拆链**：把问题拆成“实体 A → 属性/关系 → 实体 B”的链条。  
2. **先锚后扩**：先锁定最易检索的实体（专有名词、缩写、数字），再以其为关键词扩展搜索。  
3. **逐跳验证**：每拿到一条新信息，立即回代到原问题验证是否满足下一跳条件。  
4. **用结构化源优先**：维基百科、官方报告、权威数据库通常一次给出多跳所需字段，优先使用。

## 标准执行流程
1. **识别锚点**  
   用命名实体识别或关键词抽取，找出问题中最独特、最少歧义的词（人名、地名、缩写、年份）。  
   例：WPGG、Norman Allen Adie、Christian Mann、Hvalbiartunnilin。

2. **构造第一跳查询**  
   用锚点 + 限定词快速定位主体页面或权威摘要。  
   模板：`"{anchor} site:wikipedia.org"` 或 `"{anchor} {限定词}"`。

3. **提取桥接字段**  
   在返回的摘要或信息框里找到“下一步所需的键”——通常是另一实体名、地点、日期。  
   例：WPGG → Atlantic City；Norman Allen Adie → Los Alamos National Lab。

4. **构造第二跳查询**  
   用上一步得到的桥接字段作为新锚点，继续检索缺失属性。  
   模板：`"{bridge_entity} {target_attribute}"` 或 `"{bridge_entity} {event} date"`。

5. **交叉验证**  
   至少用 2 个独立来源确认同一事实；若冲突，回到步骤 2 调整关键词或限定条件。

6. **整合答案**  
   把各跳结果按逻辑顺序拼接成一句话，确保覆盖问题所有限定条件。  
   例：Atlantic City 的第一家赌场是 Resorts Casino Hotel，于 1978 年 5 月 26 日开业。

7. **格式化输出**  
   按题目要求用 `\boxed{}` 或列表形式给出最终答案，并附关键来源链接。

## 检索策略模板
- 第一跳（定位实体）：`"{entity_name} site:en.wikipedia.org"`  
- 第二跳（查属性）：`"{bridge_entity} "{attribute_phrase}" filetype:pdf OR site:gov OR site:org"`

## 补充策略 (from dataset mining: multi_hop_bridge)

### 核心原则
1. **先拆桥点**：明确必须先确定的“中间键”（人、地、时、机构）。  
2. **独立验证**：把每段子问题当作独立查询，分别找可靠来源确认。  
3. **链式引用**：用第一段答案作为第二段查询的关键词，确保上下文一致。  
4. **回环校验**：最终把多段信息拼回原始问题，检查逻辑闭环且无断层。

### 标准执行流程
1. **问题解析**  
   划出所有实体与属性，标出必须先确定的”桥点”。  
   例：*“Bajazet 的作曲家出生地的瘟疫次数” → 桥点 = 作曲家 & 出生地*

2. **首段查询**  
   用 `{主实体} {关键属性} site:wikipedia.org` 锁定桥点。  
   例：`Bajazet composer birthplace`

3. **验证桥点**  
   确认来源一致且唯一；若出现歧义，用附加限定词再搜。  
   例：`Bajazet opera composer Vivaldi birthplace`

4. **次段查询**  
   用已验证的桥点作为新主语，追问下一属性。  
   例：`plague outbreaks {birthplace} history`

5. **交叉核对**  
   至少两个独立来源确认每段结果；时间、地点、人名需完全对齐。

6. **整合回答**  
   按“桥点→追问→结论”顺序写清推理链，附引用。

7. **回环检查**  
   把最终答案代入原问题朗读，确保无缺失逻辑。

### 检索策略模板
1. 首段锁定桥点  
   `{主实体} {关键属性} site:wikipedia.org`  
   例：`Jennifer Hudson American Idol season`

2. 次段追问细节  
   `{桥点} {待追问属性} {限定条件}`  
   例：`American Idol Season 3 winner`

