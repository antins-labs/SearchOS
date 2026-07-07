---
name: data_spec_retrieval
description: 从分散的OEM/官方来源提取精确数值型规格参数并归一化（单位换算、格式标准化）
trigger: 需要精确数值参数（轮距、功率、价格等）且可能分散在多个detail页面
success_rate: 0.0
status: seed
trigger_conditions:
  domain:
  - technical
  - product
  - demographic
  - financial
  entity_types:
  - product
  - model
  - geographic_region
  - company
  attribute_types:
  - spec
  - parameter
  - datasheet
  - timeseries
  - census
  - financial_metric
  - financial_statement
cost_hint: mid
effectiveness_score: 0.0
---

# Skill: Data & Spec Retrieval（精确规格参数提取与归一化）

## 目标
解决以下两类问题：
1. **精确数值提取**：从 OEM 官方技术文档、认证文件或监管申报文档中提取精确数值型参数（轴距、功率、质量等），避免从媒体文章获取被四舍五入或版本混淆的数据。
2. **数据归一化**：当原始数据来自多个来源、单位不统一时，通过代码进行标准化换算和格式化输出。
3. **时间序列统计提取**：从国家统计机构提取历年人口、经济等时间序列数据，并进行格式化输出。
4. **财务指标精确提取**：从上市公司官方财报（SEC 10-K/10-Q）或投资者关系文件中提取精确财务数据（营收、净利润等），避免媒体转载数据的偏差。

核心策略：**溯源提取 -> 单位换算 -> 交叉验证**。

## 适用场景
1. **精确数值查询**：需要毫米级精度的轴距、轮距、离地间隙等
   - 例："Porsche 911 GT2 RS MR 的精确轴距是多少英寸？"
2. **认证参数验证**：需要官方认证文件中的技术参数
   - 例："从 EPA 申报文件中获取 Tesla Model S Plaid 的整备质量"
3. **多实体规格对比**：需要同一标准下的技术参数对比
   - 例："对比 Aventador SVJ 和 Huracan STO 的轴距差异"
4. **混合单位数据编译**：原始数据源单位不统一，需要归一化为统一格式输出
   - 例："编译 AK 枪族列表，长度用 mm，射速用 rpm"
5. **中国本土行业数据**：需要阿里云、腾讯云、华为云等中国厂商的 2025 年企业客户数、市场份额等财务/运营指标
   - 例："2025 年阿里云、腾讯云、华为云的企业客户数量分别是多少？"
6. **人口与经济统计数据**：需要国家或地区的人口、GDP、就业率等历年统计数据
   - 例："Canada population statistics for 2015-2024 with Male/Female breakdown"
7. **上市公司财务数据提取**：需要从官方财报文件中提取精确的美元金额营收、利润等数据
   - 例："Tesla 2024 年营业收入是多少美元"

## 不适用场景
- 概念性描述查询（如"操控感受如何"）
- 主观评价数据（如"最佳驾驶模式"）
- 可通过常规百科文章直接获得的基础参数（如发动机排量）
- 原始数据完全缺失的场景（本技能无法凭空生成数据）

## 核心原则

### 原则1：溯源优先
始终优先查找 OEM 官方技术文档、认证机构原始文件，而非二手转载。
优先顺序：认证文件 > 官网规格表 > 技术手册 > Wikipedia infobox > 媒体评测。

### 原则2：版本特异性
区分车型年款、特别版本（如 MR、CS、Performance 等后缀）。
同名系列可能包含多个子型号（如911系列含 Carrera/Turbo/GT3），参数可能不同。

### 原则3：检索与合成解耦
不要试图在搜索阶段强制匹配目标单位。
先以"宽容模式"检索所有相关原始数据（接受混合单位），再在合成阶段用代码进行标准化。

### 原则4：交叉验证
同一参数至少从2个独立官方来源确认。
对于单位换算，必须使用代码执行，严禁依赖大语言模型隐式推理进行数值转换。

### 原则5：维度数据库优先
当查询的参数是**标准化车辆尺寸**（轴距、轮距、长/宽/高、整备质量等）时，优先使用权威维度数据库一次性批量获取，而非逐车访问 OEM 页面。
推荐数据库：
- automobile-catalog.com
- carfolio.com
- ultimatespecs.com
- 官方 VIN 解码数据库（NHTSA、KBA）

### 原则6：中国本土数据源优先
当查询中国厂商（阿里云、腾讯云、华为云等）的**财务/运营指标**（市场份额、企业客户数、营收）时，优先使用以下中文权威来源：
- 官方财报（PDF，关键词：`年报`、`业绩快报`、`财务报告`）
- IDC/CCID/赛迪顾问等第三方行业白皮书（PDF，关键词：`中国云计算市场份额`、`中国公有云市场跟踪报告`）
- 官方新闻稿（关键词：`截至2025年`、`企业客户突破`）
- 查询模板：`"{厂商名} 2025年 企业客户数" filetype:pdf site:*.cn`
- 查询模板：`"{厂商名} 2025年 市场份额" IDC OR CCID filetype:pdf`

### 原则7：国家统计机构优先
当查询人口、经济等**时间序列统计数据**时，优先访问国家统计机构官网，而非百科全书。
- **权威来源**：Statistics Canada (statcan.gc.ca)、US Census Bureau (census.gov)、National Bureau of Statistics of China (stats.gov.cn)。
- **原因**：百科全书通常只提供汇总数据或最新年份数据，缺乏详细的历年细分（如按性别、年龄组拆分的时间序列）。
- **查询重点**：查找 "Annual Demographic Estimates" 或 "Time Series" 格式的官方表格。

### 原则8：官方财报优先
当查询上市公司财务数据（营收、净利润、现金流）时，优先查找官方 SEC 文件（10-K/10-Q）或投资者关系（IR）发布的财报原文，而非财经媒体摘要。
优先顺序：SEC EDGAR 原始文件 > 官方 IR 新闻稿 > 财经数据平台（Yahoo Finance/Bloomberg） > 财经新闻报道。
**注意**：财务数据需精确到具体年份和报告类型（年报 10-K 或季报 10-Q），避免将季度数据误认为年度数据。

## 执行流程

### Step 1：精确定位文档源
1. 使用车型/实体全称 + 年份 + 具体参数 + 文档类型构建查询
2. 优先搜索顺序：
   - **国家统计机构官网**（若为人口/经济数据）
   - **官方财报/SEC文件**（若为上市公司财务数据）
   - **标准化维度数据库**（若参数为轴距/轮距/长宽高等）
   - 制造商官网技术规格页面
   - 认证机构数据库（EPA、ECE、CCC）
   - 官方 PDF 技术手册
   - 监管申报文件（NHTSA、KBA）
   - **中国本土数据源**（若为中国厂商财务/运营指标）

**查询模板**：
- OEM 官网：`"{精确型号} {年份} {参数名}" site:{制造商域名} (specifications OR dimensions)`
- 认证文件：`"{型号} {参数名}" (filetype:pdf) (homologation OR certification OR "type approval")`
- **维度数据库**：`site:automobile-catalog.com "{精确型号}" wheelbase OR dimensions`
- **中国财报**：`"{厂商名} 2025年 企业客户数" filetype:pdf site:*.cn`
- **中国行业报告**：`"中国云计算市场份额 2025" IDC OR CCID filetype:pdf`
- **国家统计数据**：`"{国家名} population estimates {年份范围}" site:{统计机构域名}`
- **人口细分数据**：`"{国家名} population male female statistics" site:stats.gov OR site:census.gov filetype:xls OR filetype:csv`
- **上市公司财报**：`"{公司名} {年份} revenue" site:sec.gov OR site:ir.{公司域名}`
- **年报检索**：`"{公司名} {年份} 10-K" filetype:pdf`

### Step 2：结构化数据提取
1. 查找技术规格表或统计汇总表（标题含 Specifications、Technical Data、Dimensions、Population Estimates、Consolidated Statements）
2. 识别数值表格中的目标字段
3. 确认单位（mm/inches/kg/lbs）或统计口径（年中/年底人口）、财务单位（Millions/Thousands）

### Step 3：单位换算与归一化
使用代码执行换算，常用公式：
- 轴距：`mm / 25.4` -> 英寸（保留1位小数）
- 质量：`kg * 2.20462` -> 磅（取整）
- 功率：`kW * 1.341` -> hp
- 人口：四舍五入到指定位数（如 `round(x, -4)` 取整到万位）
- 财务：检查单位标注，如 "in millions" 则需乘以 1,000,000

对混合单位数据：
1. 解析原始数值字符串（如 "870 mm"、"2.9 ft"、"$96.77 billion"）
2. 定义单位转换函数，将异构单位转换为目标单位
3. 处理缺失值（标记为 "N/A"）和范围值（如 "600-650"）

### Step 4：交叉确认
1. 从至少2个不同官方文档确认同一数值
2. 核对版本号或统计年份确保版本正确
3. 检查是否有中期改款或统计口径调整导致的参数变化
4. 生成最终表格，确保所有列和行完整