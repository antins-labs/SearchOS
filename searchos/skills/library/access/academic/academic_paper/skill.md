---
name: academic_paper
description: 搜索学术论文（Semantic Scholar + DBLP + arXiv 三源并行），返回标题、作者、摘要、引用数、链接
layer: access
trigger: 查询涉及学术论文、科研文献、预印本、论文引用量、特定学术会议/期刊论文的具体内容，并且网页、新闻、微信公众号等内容无法提供详情信息时使用。
trigger_conditions:
  domain: [academic, research]
  entity_types: [paper, researcher, conference, journal]
  attribute_types: [citation_count, publication_year, venue, authors, abstract]
  coverage_gap_pattern: academic_reference_missing
cost_hint: low
effectiveness_score: 0.0
success_rate: 0.0
status: seed
has_executor: true
---

# Skill: Academic Paper Search（学术论文搜索）

## 目标
通过 Semantic Scholar、DBLP、arXiv 三个免费学术 API 并行搜索论文，返回结构化的论文元数据。

## 适用场景
1. 查找特定主题的学术论文（如 "transformer architecture"）
2. 按年份范围筛选论文（如 2023-2025 年的最新研究）
3. 查找特定作者、会议、期刊的论文
4. 需要论文引用量对比
5. 查找 arXiv 预印本和摘要

## 不适用场景
- 非学术内容（新闻、博客、产品文档）
- 需要论文全文（本 skill 仅返回元数据和摘要）
- 需要中文学术论文（建议用知网等数据源）

## 执行方式
```python
result = await execute({
    "query": "large language model alignment",
    "num_results": 5,
    "year_range": "2023-2025",
    "source": "all"  # 可选: all, semantic_scholar, dblp, arxiv
}, browser)
```

## 数据源说明
- **Semantic Scholar**: 覆盖面广，有引用量和摘要，免费无需 API key
- **DBLP**: CS 领域权威书目，元数据精确，无摘要和引用量
- **arXiv**: 预印本，有完整摘要，无引用量

## 常见误区 (Anti-Patterns)

- **场景**: When searching for papers accepted to a future or very recent conference (e.g., 'ACL 2026' when the date is April 2026, prior to the conference date).
  - ❌ 踩坑: Querying academic indices (Semantic Scholar/arXiv) with filters like 'year:2026' or 'venue:ACL 2026', or expecting these engines to return results for accepted papers not yet in proceedings.
  - 原因: Academic indices index *published* proceedings. During the acceptance phase (months before the conference), papers exist on author homepages or institutional news, but lack the 'Conference Year' metadata tag in academic databases. Searching the index yields zero results.
  - ✅ 应改用: Switch to 'news_search' or 'wechat_article' to find 'Accepted Papers Lists' (录用名单) released by institutions. Only use academic_paper to verify specific titles found in news, or wait until the conference starts to use venue filters.
  - _来源 trace: 帮我梳理一下国内主流NLP组ACL2026发表情况_ _(2026-04-20)_

- **场景**: Searching for papers from a major conference for the current year (e.g., 'ACL 2026' in April 2026), specifically when the conference has not yet occurred or proceedings are not yet online.
  - ❌ 踩坑: Querying standard academic indexes (Semantic Scholar, DBLP, arXiv) or generic web search for 'ACL 2026 papers', resulting in zero results or outdated 'Call for Papers' pages.
  - 原因: Standard academic indexes have an indexing lag; they ingest metadata only after proceedings are published or preprints are uploaded. They do not track 'accepted lists' which exist in a separate interim state.
  - ✅ 应改用: Switch to 'Accepted Papers' lists on the official conference website or OpenReview.net. For tracking specific regional groups (e.g., Chinese labs), pivot to institutional news releases or `wechat_article` searches, as labs self-report acceptances immediately upon notification, bypassing the academic index lag.
  - _来源 trace: 帮我梳理一下国内主要 NLP 及相关研究组发表 ACL 2026 论文的情况。_ _(2026-04-22)_

- **场景**: When searching for papers from a specific upcoming or very recent conference edition (e.g., 'ACL 2026' when the date is April 2026, before proceedings are out).
  - ❌ 踩坑: Using standard academic search engines (Semantic Scholar, DBLP) with the query 'Conference Name + Year' (e.g., 'ACL 2026').
  - 原因: Bibliographic databases rely on proceedings metadata. Before the conference proceedings are formally published, papers are often indexed only as arXiv preprints without the 'ACL 2026' tag, or not indexed at all yet.
  - ✅ 应改用: Switch to 'Accepted Papers' lists on the official conference website or OpenReview; OR use News/Social Search (e.g., WeChat articles, lab homepages) to find 'Acceptance' announcements from specific research groups.
  - _来源 trace: 帮我梳理一下国内主要 NLP 及相关研究组发表 ACL 2026 论文的情况。_ _(2026-04-23)_

- **场景**: when searching for very new or niche technical terms (<12 months old) that may not yet be indexed in academic databases
  - ❌ 踩坑: academic_paper skill directly searching for 'Agent Harness Engineering' - returned 0 results across all 3 sources (Semantic Scholar, DBLP, arXiv)
  - 原因: Emerging technical terms may not appear in indexed academic databases yet, especially if they are new to the field. The skill assumes indexed content exists, which is not guaranteed for cutting-edge topics.
  - ✅ 应改用: Use reverse_clue_search to find related papers indirectly, combine with github_readme for code repositories, or use multi_hop_bridge to discover the topic through related concepts first before attempting direct academic search
  - _来源 trace: 梳理 Agent Harness Engineering 的最新发展趋势。_ _(2026-04-23)_

