# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

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

### CLI 调用（推荐）
```bash
# 使用连字符格式的命令行选项
python scripts/run.py --query "OpenAI GPT-5 release" --num-results 5 --days-back 7

# 或使用 JSON 参数
python scripts/run.py --params '{"query": "OpenAI GPT-5 release", "num_results": 5, "days_back": 7}'
```

**注意：命令行选项必须使用连字符格式（`--num-results`、`--days-back`），不支持下划线格式（`--num_results`、`--days_back`）。**

### 代码调用
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
