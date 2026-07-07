# 163.com Article Extractor

Extracts content and metadata from NetEase (163.com) news articles.

## Features

### get_article
Extracts full article content and metadata from 163.com dy articles.

**Parameters:**
- `url` (string, optional): Full article URL, e.g., `https://www.163.com/dy/article/K6RS1LNS0553WOHP.html`
- `article_id` (string, optional): Article ID like `K6RS1LNS0553WOHP` (alternative to url)

**Returns:**
```json
{
  "success": true,
  "article_id": "K6RS1LNS0553WOHP",
  "url": "https://www.163.com/dy/article/K6RS1LNS0553WOHP.html",
  "title": "文章标题",
  "author": "作者/来源网站",
  "source": "来源媒体名称",
  "location": "地区",
  "publish_time": "2025-08-13 16:10:03",
  "keywords": "关键词列表",
  "description": "文章摘要",
  "content": "文章正文内容...",
  "content_length": 376,
  "images": [
    {
      "url": "https://...",
      "alt": "图片描述"
    }
  ],
  "image_count": 1,
  "related_articles": [
    {
      "article_id": "XXXXXXXX",
      "title": "相关文章标题",
      "url": "https://..."
    }
  ]
}
```

### get_comments
Gets comment statistics and metadata for an article.

**Parameters:**
- `article_id` (string, required): Article ID like `K6RS1LNS0553WOHP`

**Returns:**
```json
{
  "success": true,
  "article_id": "K6RS1LNS0553WOHP",
  "title": "文章标题",
  "url": "文章链接",
  "doc_id": "文档ID",
  "create_time": "发布时间",
  "modify_time": "修改时间",
  "comment_count": 2,
  "reply_count": 3,
  "read_count": 150,
  "vote": 0,
  "against": 0,
  "board_id": "板块ID",
  "business_id": "业务ID",
  "business_type": 8
}
```

## Usage Examples

### Extract article by URL
```python
result = await execute({
    'function': 'get_article',
    'url': 'https://www.163.com/dy/article/K6RS1LNS0553WOHP.html'
})
```

### Extract article by ID
```python
result = await execute({
    'function': 'get_article',
    'article_id': 'K6RS1LNS0553WOHP'
})
```

### Get comment statistics
```python
result = await execute({
    'function': 'get_comments',
    'article_id': 'K6RS1LNS0553WOHP'
})
```

## Notes

- Article URLs are in the format: `https://www.163.com/dy/article/{ARTICLE_ID}.html`
- Article IDs are uppercase alphanumeric strings (e.g., `K6RS1LNS0553WOHP`)
- Content is extracted from the `.post_body` div element
- Images are extracted with their URLs and alt text
- Related articles are limited to 10 items max
- The comment API provides statistics only, not actual comment content
- Direct HTTP requests are used (no browser automation needed)
- Rate limiting: Be respectful when making multiple requests

## Supported Sites

- 163.com dy articles (网易订阅文章)
- URL pattern: `https://www.163.com/dy/article/*.html`

## Error Handling

All errors are returned in the response with `success: false`:
```json
{
  "success": false,
  "error": "Error description",
  "article_id": "..."
}
```