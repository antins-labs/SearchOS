---
name: deep_web_explorer
description: 从需要表单交互或特定查询参数的深网数据库接口中提取结构化数据
trigger: 目标数据隐藏在动态数据库表单之后（如.gov科学数据库、公共记录库），标准搜索引擎无法索引
success_rate: 0.0
status: seed
trigger_conditions:
  domain:
  - general
  entity_types:
  - any
  attribute_types:
  - any
  coverage_gap_pattern: surface_web_dry
cost_hint: high
effectiveness_score: 0.0
---

# Deep Web Explorer (深网数据库探索)

## 1. 目标
解决标准搜索引擎无法索引或检索“深网”内容的问题。此类内容通常存在于动态数据库、政府数据门户或需要表单交互的系统中。该技能旨在通过直接与数据库查询接口交互，构建特定的查询参数或模拟表单提交，从而获取结构化的数据结果，避免在静态搜索结果中陷入死循环。

## 2. 适用场景
- **动态数据库查询**：目标数据隐藏在查询表单之后（如 `.gov` 域名的科学数据库、公共记录库）。
- **结构化筛选需求**：问题包含明确的筛选条件（如“列出所有状态为‘Threatened’的鸟类”），这通常对应数据库的下拉菜单或复选框。
- **标准搜索失败**：使用普通关键词搜索仅能找到“搜索入口页面”或“免责声明”，而非具体数据列表。
- **特定领域门户**：ECOS (U.S. Fish & Wildlife), SEC Edgar, 专利数据库, 学术资源库等。

## 3. 不适用场景
- **静态内容获取**：数据直接存在于静态HTML页面中（如新闻文章、博客、维基百科）。
- **纯导航任务**：仅需找到网站首页或特定登录入口。
- **需要登录鉴权**：目标数据库需要用户名密码登录（除非已有cookie），本技能仅处理公开但需交互的接口。

## 4. 核心原则
1.  **接口优先，搜索在后**：一旦识别出目标是数据库接口，停止使用通用搜索引擎寻找“结果页”，转而分析当前页面的表单结构。
2.  **参数化思维**：将自然语言需求转化为数据库可识别的查询参数（如 `status=Threatened`, `taxon=Bird`），而不是构建长难句关键词。
3.  **直接交互**：通过 `open` 配合特定参数直接访问查询结果页（如果URL模式已知），或使用 `click`/`type` 操作表单元素。

## 5. 标准执行流程

### 步骤 1：识别与定位
- **动作**：访问已知的数据库根目录或通过通用搜索找到数据库的“查询入口”。
- **判断**：检查页面是否包含 `<form>` 标签、搜索栏、下拉筛选器。
- **关键点**：如果页面标题包含 "Database", "Search", "Query", 或 "Report"，立即切换到此技能模式。

### 步骤 2：逆向工程表单/URL
- **动作**：分析表单元素。
    - 寻找 `<select>` 标签对应的选项值（例如，页面上显示 "Threatened"，但 `value` 可能是 "T" 或 "2"）。
    - 观察 URL 结构：尝试进行一次手动查询，观察 URL 变化（例如从 `search.html` 变为 `results.html?status=T&group=Bird`）。
- **目的**：确定构建直接查询请求所需的参数名和参数值。

### 步骤 3：构建深度查询
- **动作**：根据步骤 2 获取的信息，构建直接访问结果页的指令。
- **策略**：
    - **URL 构造法（推荐）**：如果 URL 参数清晰，直接 `open` 到构造好的 URL（如 `.../species?status=Threatened&class=Bird`）。这比模拟点击更节省步骤。
    - **表单模拟法**：如果 URL 不变（POST请求）或参数加密，则需模拟输入：`type "Bird" into search_box`, `click "Threatened" checkbox`, `click "Submit"`。

### 步骤 4：验证与提取
- **动作**：检查返回页面是否包含数据表格或列表。
- **验证**：确认结果数量是否大于 0，且字段匹配需求。
- **翻页处理**：如果数据分页，寻找 "Next" 按钮或修改 URL 中的 `page`/`offset` 参数。

## 6. 检索策略模板

### 模板 A：URL 参数直接构造法
适用于 GET 请求的数据库接口。
```text
open url="[Database_Base_URL]/[Search_Script]?[Param1]=[Value1]&[Param2]=[Value2]"
```
*示例*:
`open url="https://ecos.fws.gov/ecp0/reports/ad-hoc-species-report?kingdom=Animal&class=Aves&status=Threatened"`

### 模板 B：表单交互法
适用于复杂的 POST 请求或 JavaScript 渲染的表单。
```text
open url="[Database_Search_Page_URL]"
find "Status" # 确认加载完成
click "checkbox[value='Threatened']"
click "button[type='submit']"
```

## 7. 示例

**任务**: Search the U.S. Fish & Wildlife Service ECOS database for all bird species listed as "Threatened".

**执行过程**:

1.  **初步定位**:
    - 代理识别出 `ecos.fws.gov` 是一个数据库接口。
    - *错误路径 (旧方法)*: 在 Google 搜索 "ECOS threatened birds" -> 找不到具体列表 -> 循环搜索 -> 预算耗尽。
    - *正确路径 (本技能)*: 直接访问 ECOS 的物种报告生成器页面。

2.  **分析接口**:
    - `open "https://ecos.fws.gov/ecp0/reports/ad-hoc-species-report"`
    - 观察到该页面支持通过 URL 参数进行筛选。通过查看页面源码或经验判断，参数可能为 `kingdom` (界), `class` (纲), `status` (状态)。

3.  **构建查询**:
    - 需求映射：
        - "Bird species" -> `class=Aves` (鸟类学名)
        - "Threatened" -> `status=Threatened`
    - 构造 URL: `https://ecos.fws.gov/ecp0/reports/ad-hoc-species-report?kingdom=Animal&class=Aves&status=Threatened`

4.  **获取数据**:
    - 执行 `open url="https://ecos.fws.gov/ecp0/reports/ad-hoc-species-report?kingdom=Animal&class=Aves&status=Threatened"`
    - 页面直接加载出包含所有受威胁鸟类的表格。
    - 使用 `find` 或解析表格内容提取数据。

**结果**: 成功绕过无效的通用搜索，直接从深网数据库提取结构化数据。

## 补充策略 (from dataset mining: web_deep_navigation)

### 核心原则
1. **先拆后合**：把复合问题拆成可独立验证的最小事实单元，再按优先级排序。
2. **先官方后次级**：优先锁定最权威或最精确的来源（官网、权威媒体、政府公报），再向外扩散。
3. **时间-地点双锚**：用”时间窗口 + 地点/实体”作为首轮关键词，快速缩小范围。
4. **交叉验证**：同一事实至少两个独立来源确认，数值类需核对原始出处。

### 标准执行流程
1. **问题解析**  
   用一句话重述问题，并列出所有必须满足的子条件（≥2 个）。  
   例：需同时满足“Marcelo Arévalo + 2010-2014 + São Paulo + 单打冠军”。

2. **优先级排序**  
   按“最易锁定 → 最难锁定”排序。通常：特定报道标题 > 数值/事实 > 宽泛事件。

3. **首轮精准搜索**  
   用“实体 + 最强限定词”构造查询：`"Marcelo Arévalo" "São Paulo" 2010..2014 singles winner site:atptour.com`。

4. **结果缺口识别**  
   若首轮无直接答案，记录缺失信息（如只找到双打记录），准备二次拆解。

5. **次级扩展搜索**  
   放宽或替换限定词，引入次级来源：`"Marcelo Arévalo" São Paulo challenger 2012 site:flashscore.com OR site:itftennis.com`。

6. **交叉验证**  
   对关键事实（冠军名称、数值、日期）至少找到两条独立来源；若冲突，标记并溯源。

7. **整合与摘要**  
   将各子事实拼接成最终答案，注明来源与置信度；如仍有缺口，明确说明“未找到”。

8. **存档与模板化**  
   把有效 query 模板与来源列表保存，供后续同类问题复用。

### 检索策略模板
1. 指定报道提取：`"{exact_title}" site:bbc.co.uk`  
2. 时间-地点-实体：`"{entity}" "{location}" {start_year}..{end_year} "{keyword}"`


