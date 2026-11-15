---
name: aiweekly-co
description: 从 aiweekly.co 获取 AI 新闻摘要，支持按日期查询每日新闻记录
metadata:
  searchos-category: access
  host: aiweekly.co
---

# AI Weekly 新闻访问技能

从 aiweekly.co 获取结构化的 AI 新闻记录。

## 能力概览

| 能力 ID | 用途 | 命令示例 |
|---------|------|----------|
| `get_news_by_date` | 获取指定日期的 AI 新闻摘要 | `python scripts/access.py get_news_by_date --input '{"date": "October 19"}'` |

## 命令说明

### get_news_by_date

获取指定日期的 AI 新闻摘要页面，返回该日的结构化新闻记录。

**输入参数：**
- `date` (必需): 目标日期，格式如 `"October 19"` 或 `"September 15"`

**输出字段：**
- `date`: 请求的日期
- `title`: 新闻标题
- `summary`: 新闻摘要
- `source_url`: 新闻来源链接（aiweekly.co/alerts 页面或外部来源）
- `canonical_url`: 原始来源 URL（与 source_url 相同，避免额外请求）
- `category`: 新闻分类（如 "AI Business", "Research", "Security" 等）
- `time_ago`: 发布时间（如 "Oct 19", "Sep 14"）

**示例：**
```bash
python scripts/access.py get_news_by_date --input '{"date": "October 19"}'
```

**输出格式：**
```json
{
  "status": "ok",
  "records": [
    {
      "date": "October 19",
      "title": "Anthropic Commits 5% of Equity to New Public Benefit Fund",
      "summary": "Anthropic says it will commit 5% of its shares...",
      "source_url": "https://aiweekly.co/alerts/...",
      "canonical_url": "https://aiweekly.co/alerts/...",
      "category": "Frontier Labs",
      "time_ago": "Oct 18"
    }
  ],
  "warnings": []
}
```

## 错误处理

- **非法输入** (`status: invalid_input`): 缺少必需字段或 JSON 格式错误，返回非零退出码
- **网络错误** (`status: error`): HTTP 错误或网络问题，返回非零退出码
- **无匹配结果** (`status: ok`, `records: []`): 指定日期无可用新闻，返回空记录和警告信息

## 依赖

- Python 3.7+
- 标准库: `urllib`, `ssl`, `re`, `html`, `json`, `argparse`

## 限制

- 每日版归档页面仅列出最近约 3 个月的日期（从 2026 年 7 月起）
- 新闻条目的时间戳为相对时间（如 "Oct 19"），未提供精确发布时间
- 本技能仅覆盖公开可访问的每日新闻页面，不涉及登录内容或订阅内容

## 参考文献

- [capabilities.md](references/capabilities.md): 站点能力详细说明