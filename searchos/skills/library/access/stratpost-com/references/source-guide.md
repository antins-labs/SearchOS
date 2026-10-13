# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# StratPost Access Skill

Extracts defense and security news articles from [StratPost](https://stratpost.com), a leading online defense and aerospace news portal.

## Features

### get_article
Extract full content from a StratPost article URL.

**Parameters:**
- `url` (required): Full URL of the article

**Returns:**
- Article title, author, publication date
- Full article content
- Featured image URL
- Categories and tags
- Meta description

**Example:**
```python
{
    "function": "get_article",
    "url": "https://stratpost.com/sipri-wars-push-global-arms-sales-to-all-time-high/"
}
```

### get_latest
Get the latest articles from the StratPost homepage.

**Parameters:**
- `limit` (optional): Maximum number of articles to return (default: 20)

**Returns:**
- List of recent articles with title, URL, date, excerpt, author, and thumbnail

**Example:**
```python
{
    "function": "get_latest",
    "limit": 10
}
```

### search
Search for articles on StratPost.

**Parameters:**
- `query` (required): Search keyword or phrase
- `limit` (optional): Maximum number of results to return (default: 20)

**Returns:**
- List of matching articles with title, URL, date, excerpt, and author

**Example:**
```python
{
    "function": "search",
    "query": "ukraine",
    "limit": 15
}
```

## Content Coverage

StratPost covers:
- Defense industry news and analysis
- Military technology and procurement
- Aerospace and space defense
- Geopolitical security issues
- NATO and European defense matters
- Arms trade and defense contracts

## Notes

- The site uses WordPress with a standard article structure
- Articles typically include detailed reporting on defense matters
- Content is suitable for research on military and security topics
- Direct HTTP requests are used (no JavaScript rendering required)
