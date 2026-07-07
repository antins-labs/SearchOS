---
name: wechat_article
description: 搜索微信公众号文章并提取全文（通过 Sogou 微信搜索），返回标题、真实 URL、发布时间、正文内容
layer: access
trigger: 查询涉及微信公众号、中文社交媒体内容、或明确需要微信文章时触发
success_rate: 0.0
status: seed
has_executor: true
trigger_conditions:
  domain:
  - news
  - blog
  - social
  entity_types:
  - article
  - author
  attribute_types:
  - author
  - content
  - publication_date
cost_hint: mid
effectiveness_score: 0.0
---

# Skill: WeChat Article Search（微信公众号文章搜索）

## 目标
通过 Sogou 微信搜索引擎搜索微信公众号文章，解析真实 URL 并提取文章全文。

## 适用场景
1. 搜索微信公众号文章（中文内容）
2. 需要从微信获取行业分析、技术博客等内容
3. 查找特定话题在微信生态中的讨论

## 不适用场景
- 非微信平台内容
- 英文搜索（建议用 web_search）
- Sogou 反爬验证触发时（需稍后重试）

## 执行方式
```python
result = await execute({
    "query": "大模型 RAG 技术",
    "num_results": 5,
    "fetch_content": True
}, browser)
```

## 技术管线
1. **Sogou 搜索**: 搜索 `weixin.sogou.com`，XPath 提取标题和代理链接
2. **URL 解析**: 从 Sogou 代理页面的 JS 拼接中提取真实 `mp.weixin.qq.com` URL
3. **内容提取**: 获取文章页面，从 `#js_content` 提取纯文本

## 注意事项
- 无需 API key，但可能触发 Sogou 反爬验证
- 文章内容截断为 3000 字符
- 依赖 `httpx` 和 `lxml`
