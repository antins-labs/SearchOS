# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Crystalinks Pyramid Articles Access Skill

This skill fetches article content from Crystalinks.com, a website containing extensive information about Egyptian pyramids, pharaohs, and ancient civilizations.

## Features

- **Robust encoding handling**: Automatically handles pages encoded in UTF-8, Windows-1252, ISO-8859-1, and Latin-1
- **Content extraction**: Extracts title, paragraphs, images, and related links
- **Noise filtering**: Removes navigation links, footers, and duplicate content
- **Concurrent fetching**: Supports batch requests for multiple articles

## Functions

### get_article

Fetches a single article by URL or slug.

**Parameters:**
- `url`: Full URL or slug (required)

**Example:**
```python
# Using full URL
result = await execute({
    'function': 'get_article',
    'url': 'https://www.crystalinks.com/pyrkhendjer.html'
}, ctx)

# Using slug
result = await execute({
    'function': 'get_article',
    'url': 'pyrkhendjer'
}, ctx)
```

**Returns:**
```json
{
    "url": "https://www.crystalinks.com/pyrkhendjer.html",
    "title": "Pyramid of Khendjer at South Saqqara",
    "content": ["Paragraph 1...", "Paragraph 2...", ...],
    "images": [{"url": "...", "alt": ""}, ...],
    "links": [{"url": "...", "text": "..."}, ...],
    "error": null
}
```

### get_multiple_articles

Fetches multiple articles concurrently.

**Parameters:**
- `urls`: List of URLs or slugs (required)
- `max_concurrent`: Maximum concurrent requests (default: 5)

**Example:**
```python
result = await execute({
    'function': 'get_multiple_articles',
    'urls': ['pyrkhendjer', 'zawyet', 'pyrmazghuna']
}, ctx)
```

### search_pyramid_pages

Searches for pyramid-related pages by keyword.

**Parameters:**
- `keyword`: Search keyword (optional)

**Example:**
```python
# Find all Saqqara-related pages
result = await execute({
    'function': 'search_pyramid_pages',
    'keyword': 'saqqara'
}, ctx)

# List all known pyramid pages
result = await execute({
    'function': 'search_pyramid_pages'
}, ctx)
```

## Notes

- Crystalinks pages use simple HTML structure with `<p>` tags for content
- Some pages use Windows-1252 encoding instead of UTF-8
- Navigation links are automatically filtered out from results
- Images are returned with full absolute URLs
