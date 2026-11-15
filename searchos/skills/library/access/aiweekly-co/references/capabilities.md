# AI Weekly 站点能力说明

## 站点概述

**站点**: aiweekly.co  
**类型**: AI 新闻聚合与摘要站点  
**访问方式**: 公开 HTTP 访问，无需认证

## 已验证能力

### 1. get_news_by_date

**功能**: 获取指定日期的 AI 新闻摘要

**访问路径**:
1. 访问 `https://aiweekly.co/ai-news-today/editions` 获取日期索引
2. 从索引中匹配用户输入的日期，获取对应的 edition URL
3. 访问 edition 页面（如 `https://aiweekly.co/ai-news-today/edition/2026-10-19`）
4. 解析页面中的 `<article>` 标签获取新闻条目

**输入格式**:
- `date`: 月份 + 日期，如 `"October 19"`, `"September 15"`

**日期映射规则**:
- Editions 页面格式: `<a class="dehub__item" href="/ai-news-today/edition/YYYY-MM-DD"><span class="dehub__item-date">Weekday, Month DD</span>`
- 提取 `Month DD` 作为日期键
- URL 格式: `/ai-news-today/edition/YYYY-MM-DD`

**新闻条目结构**:
```
<article>
  <div style="font-size:10.5px">Oct 19 · Source · Category</div>
  <a href="URL" style="font-size:23px">Title →</a>
  <p style="font-size:13.5px">Summary...</p>
</article>
```

**提取字段**:
- `date`: 用户输入的日期
- `title`: `<a>` 标签内的标题文本（移除末尾 "→"）
- `summary`: `<p>` 标签内的摘要文本
- `source_url`: `<a>` 标签的 `href` 属性
- `canonical_url`: 与 `source_url` 相同（避免额外请求）
- `category`: 元信息第三部分（如 "Frontier Labs", "AI Business"）
- `time_ago`: 元信息第一部分（如 "Oct 19", "Sep 14"）

**验证证据**:
- obs-1: `https://aiweekly.co/ai-news-today` 页面结构
- obs-6: `https://aiweekly.co/ai-news-today/editions` 日期索引页面
- obs-10: 日期链接提取模式
- obs-14-16: 新闻条目解析模式

**限制**:
- 归档仅包含约 3 个月的历史（从 2026 年 7 月起）
- 时间戳为相对时间，非精确发布时间
- 每个日期页面包含约 9-14 条新闻

## 未实现能力

### 获取原始来源 URL

**原因**: 每条新闻的 `source_url` 可能指向 `aiweekly.co/alerts/` 页面，该页面包含指向原始来源的链接。但为了性能考虑，不额外请求详情页。

**如需实现**:
- 访问 `https://aiweekly.co/alerts/{slug}`
- 查找 `<a>` 标签包含 "Read the original article →" 的 `href` 属性
- 示例: obs-20 显示 `https://www.anthropic.com/news/public-benefit-fund`

### 搜索功能

**原因**: 站点未提供公开的搜索 API，搜索需要登录。

### 分类筛选

**原因**: 每日页面不提供分类筛选，所有新闻混合显示。

## 错误状态

| 状态 | 含义 | 退出码 |
|------|------|--------|
| `ok` | 成功获取数据 | 0 |
| `ok` (空记录) | 日期无匹配，返回警告 | 0 |
| `invalid_input` | 输入格式错误或缺少必需字段 | 1 |
| `error` | 网络/HTTP 错误 | 1 |

## 测试用例

**成功用例**:
- `{"date": "October 19"}`: 返回 9 条新闻记录
- `{"date": "September 15"}`: 返回 14 条新闻记录

**失败用例**:
- `{}`: 返回 `invalid_input`，警告 "Missing required field: date"
- `"not json"`: 返回 `invalid_input`，警告 JSON 解析错误
- `{"date": "January 1"}`: 返回 `ok` 空记录，警告无匹配日期