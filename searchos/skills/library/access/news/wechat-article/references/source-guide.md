# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

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
