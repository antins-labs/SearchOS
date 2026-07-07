---
name: academic_retrieval
description: 从权威学术或事实来源中快速定位并提取精确信息，解决“谁/什么/何时/何地/多少”类事实问答。
trigger: 当问题要求给出具体事实（人名、机构、时间、数字、定义、属性等），且答案应来自学术论文、官方公告、权威百科或可信新闻时启用。
success_rate: 0.0
status: seed
trigger_conditions:
  domain:
  - academic
  entity_types:
  - paper
  - researcher
  - lab
  attribute_types:
  - citation
  - publication
  - venue
  - financial_metric
cost_hint: mid
effectiveness_score: 0.0
---

# academic_retrieval

## 目标
解决需要“精确事实”的问答任务：给定一个实体或事件，需返回其某一确定属性（如所属机构、出生年份、数值指标、定义、父节点等）。此类问题对来源可靠性要求高，需优先使用学术数据库、政府/机构官网、权威百科、同行评议文献等。

## 适用场景
1. 查找某人在某年所属的政治党派（例：Ramadhar Kashyap 属于哪个印度政党？）
2. 查询某机构/院系承担的国家项目数量（例：暨南大学数学系教师主持多少国家级项目？）
3. 核实某期刊或会议的出版周期（例：Latina 和 Entrepreneur 都是月刊吗？）
4. 确认某歌曲的演唱者或某电影的演员子女（例：谁演唱了《Let There Be More Light》？）
5. 获取医学综合征的定义与特征症状（例：Frey 综合征的典型症状是什么？）
6. 查询上市公司特定年份的财务指标（例：Tesla 2024 年营业收入是多少美元？）

## 不适用场景
- 需要主观评价或观点的问题（如“这部电影好看吗？”）
- 需要多步推理或计算的问题（如“如果利率上升 2%，GDP 将如何变化？”）
- 仅能通过原始实验或调查才能获得的未公开数据

## 核心原则
1. **先定位实体，再查属性**：先确认问题中的主体（人、机构、事件、概念），再针对该主体搜索其目标属性。
2. **权威来源优先**：学术数据库（Google Scholar、CNKI）、政府/机构官网、.gov、.edu、.ac.cn）、权威百科、同行评议期刊。
3. **关键词精准**：使用主体全名 + 属性关键词，必要时加限定词（年份、地点、机构）。
4. **首要权威源即停**：拿到一份权威主源（SEC filing、官方年报、Wikipedia 信息框、机构官网）就停，不要再开第二份"对比来源"——这条 skill 走的是事实型问答，单一权威主源足以。

## 标准执行流程
1. **解析问题**  
   提取“主体 + 目标属性”，用一句话重述：“我需要找【主体】的【属性】”。
2. **构造首轮查询**  
   用“主体全名 + 属性关键词 + 权威站点”模板：  
   `{entity} {attribute} site:wikipedia.org`  
   或 `{entity} "{attribute}" site:edu`。
3. **快速浏览摘要**  
   在搜索结果摘要中找含关键词的条目；若 10 条内无直接答案，进入下一步。
4. **细化或扩展关键词**  
   - 若主体名称歧义，加限定词（年份、地点、机构）。  
   - 若属性词太宽泛，换成同义词或上位词（如“children”→“son OR daughter”）。
5. **深入权威页面**  
   打开最相关的 1-2 个来源（Wikipedia 信息框、大学官网简介、期刊文章摘要），直接定位含属性字段的段落或表格。  
   - **财务/年报数据定位**：若目标为财务数据（如营收、利润），且来源为长篇年报（如 10-K），直接搜索特定报表标题（如 "Consolidated Statements of Operations" 或 "Income Statement"），而非仅搜索指标名称，以快速锁定数据表行，避免在正文段落中无效徘徊。
6. **提取并格式化答案**  
   仅提取目标属性，按问题要求格式输出（如加 \boxed{}）。
7. **记录来源**  
   在答案后附 1 条最权威来源链接或引用，方便复核。

## 检索策略模板
- **人物/机构属性**：`"{Full Name}" "{attribute}" site:edu OR site:ac.cn OR site:gov`
- **数值/统计**：`"{entity}" "{attribute}" filetype:pdf site:edu`（优先年报或官方报告）
- **财务数据/年报**：`"{Company Name}" "{Year}" "Form 10-K" OR "Annual Report" filetype:pdf`

## 补充策略

### 核心原则
1. **先拆后搜**：把问题拆成“主体 + 限定属性 + 权威来源”三要素
2. **双语并行**：中英文关键词同时构造，覆盖中外数据库
3. **站点限定**：优先 `site:edu`, `site:gov`, `site:org`, `site:ac.cn` 等权威域
4. **表格导航优先**：对于财报、统计年鉴等结构化文档，优先定位“报表标题”或“表头”，利用行提取机制获取数据，避免通篇阅读。

### 标准执行流程
1. **实体识别**：用一句话提炼”要找什么”（如”找电台 WPMR-LP 的地理位置”）
2. **关键词生成**：
   - 主体英文/中文全称 + 缩写
   - 属性关键词（location, committee member, county, definition…）
   - 同义词/近义词（ferret ≈ weasel）
3. **构造查询**：
   - 模板 A：`"{entity}" "{attribute}" site:edu OR site:gov`
   - 模板 B：`"{entity}" "{attribute}" filetype:pdf`
4. **首轮检索**：优先点击 `.edu`, `.gov`, `.ac.cn`, `.org` 域名结果
5. **溯源记录**：复制 URL + 关键段落，注明发布机构与日期
6. **格式输出**：按问题要求包装答案（如“\boxed{county name}”）

### 检索策略模板
- 机构/人物：`"{institution name}" "{role}" site:edu.cn OR site:ac.cn`
- 地点/坐标：`"{place}" county OR state site:gov OR site:wikipedia.org`
- 数据/报告：`"{report title}" "{metric}" filetype:pdf site:org`
- 财务/年报：`"{Company}" "{Year}" "10-K" "Consolidated Statements of Operations"`