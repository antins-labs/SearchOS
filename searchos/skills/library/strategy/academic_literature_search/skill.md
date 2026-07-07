---
name: academic_literature_search
description: 学术文献搜索——论文 / 方法名 / 数据集 / 基准 / 综述
trigger: 任务涉及具体论文、方法（method name）、数据集、基准测试、综述资料
layer: strategy
success_rate: 0.0
status: seed
alpha: 1
beta: 1
---
## 目标
学术检索有专门的高权威入口（arXiv / Semantic Scholar / OpenReview / Google Scholar / ACL Anthology）和专门的关键词形态（方法名 / 数据集名 / 基准名）。本 skill 给出 7 条核心规则。

## 适用场景
- 找论文原文 / 方法定义 / 数据集卡片
- 找最新 SoTA / leaderboard
- 找综述定位领域

## 规则（共 7 条）
1. **学术入口优先**：Semantic Scholar / OpenReview / arXiv / ACL Anthology / Google Scholar，比通用 Web 搜索更准。
2. **方法名 / 数据集名当实体处理**：用引号锁定 `"Chain of Thought"` / `"GSM8K"`，避免分词。
3. **优先 venue + 年份**：`NeurIPS 2023 <method>`，命中正文比博客解读更直接。
4. **综述定位领域**：进入新领域先搜 `survey` / `review`，比单篇论文更高效。
5. **代码 + 论文双向链接**：Papers with Code / 论文里的 GitHub link 用于复现与方法细节。
6. **引文图谱用 Semantic Scholar / Connected Papers**：找前置工作与后续工作。
7. **预印本与正式版差异**：arXiv 版与会议正式版可能有差别，引用结论以正式版为准。

## 执行流程
1. 识别目标类型：method / dataset / benchmark / paper / survey。
2. 选学术入口 → 引号 + venue + 年份。
3. 命中后看 abstract → 看代码仓库 → 看引文图谱。

## 关联 skill
- `official_docs_api_search` — 工业界文档
- `github_search` — 论文配套代码仓库
- `general_query_construction` — query 构造上游
