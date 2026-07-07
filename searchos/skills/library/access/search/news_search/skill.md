---
name: news_search
description: 搜索近期新闻文章（NewsAPI + Google News RSS 双源回退），返回标题、来源、日期、摘要
layer: access
trigger: 查询涉及近期新闻、时事、最新动态、"最近"、"近期"、"本周"、"本月"等时效性关键词时触发
success_rate: 0.0
status: seed
has_executor: true
trigger_conditions:
  domain:
  - news
  - current_events
  entity_types:
  - event
  - organization
  - person
  attribute_types:
  - date
  - headline
  - body
  - source
cost_hint: low
effectiveness_score: 0.0
---

# Skill: News Search（新闻搜索）

## 目标
搜索近期新闻文章，支持按时间窗口筛选，返回标题、来源、发布日期和摘要。

## 适用场景
1. 查询最新新闻和时事（"最近一周 AI 新闻"）
2. 跟踪特定话题的最新进展
3. 需要带时间戳的新闻来源作为 evidence
4. 查找特定时间段内的报道

## 不适用场景
- 历史事件（超过 30 天）
- 学术论文（使用 academic_paper skill）
- 微信公众号内容（使用 wechat_article skill）

## 执行方式
```python
result = await execute({
    "query": "OpenAI GPT-5 release",
    "num_results": 5,
    "days_back": 7
}, browser)
```

## 数据源说明
- **NewsAPI**: 全球主流英文媒体，需 `NEWSAPI_KEY` 环境变量（可选）
- **Google News RSS**: 无需 API key 的回退方案，覆盖面广
