# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Volcano Hotspot WordPress Blog Access Skill

This skill fetches content from [Volcano Hotspot](https://volcanohotspot.wordpress.com/), a WordPress blog dedicated to volcanic features, eruptions, and geological information from around the world.

## Functions

### get_post

Fetches a single blog post with full content extraction.

**Parameters:**
- `url` (required): Full URL of the blog post

**Returns:**
- `title`: Post title
- `author`: Author name
- `published_date`: Publication date (YYYY-MM-DD)
- `modified_date`: Last modified date (YYYY-MM-DD)
- `url`: Original post URL
- `categories`: List of category names
- `tags`: List of tag names
- `content`: Full text content
- `content_html`: Raw HTML content
- `paragraphs`: Structured list of content paragraphs with type and text
- `word_count`: Approximate word count
- `images`: List of images with src and alt text
- `image_count`: Number of images
- `featured_image`: Featured image if available

**Example:**
```python
result = await execute({
    'function': 'get_post',
    'url': 'https://volcanohotspot.wordpress.com/2019/08/11/are-there-volcanoes-in-fiji/'
})
```

### get_posts

Fetches a paginated list of blog post summaries from the homepage or archive pages.

**Parameters:**
- `page` (optional): Page number (default: 1)

**Returns:**
- `page`: Current page number
- `articles`: List of article summaries, each containing:
  - `title`: Post title
  - `url`: Post URL
  - `author`: Author name
  - `published_date`: Publication date
  - `categories`: List of categories
  - `tags`: List of tags
  - `excerpt`: First paragraph excerpt
  - `featured_image`: Featured image URL
- `count`: Number of articles returned

**Example:**
```python
# Get first page of posts
result = await execute({
    'function': 'get_posts',
    'page': 1
})

# Get second page
result = await execute({
    'function': 'get_posts',
    'page': 2
})
```

## Content Notes

- The blog covers volcanic features worldwide with detailed geological explanations
- Posts typically include maps, diagrams, and photographs
- Categories include geographic regions (Pacific Islands, etc.) and topics (Volcanoes)
- Tags are extracted from WordPress post classes for accurate categorization
- Content is extracted cleanly with HTML preserved for rich formatting needs

## Error Handling

The skill returns structured error responses:
- HTTP errors (429, 404, etc.) are captured with status codes
- Missing required parameters return clear error messages
- Invalid URLs (not from volcanohotspot.wordpress.com) are rejected
