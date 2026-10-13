# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# France24.com Access Skill

This skill retrieves article content and section listings from France24.com English edition.

## Functions

### get_article

Fetch full article content, title, date, and metadata from a France24 article URL.

**Parameters:**
- `url` (required): Full URL to a France24 article page

**Example:**
```
{
  "function": "get_article",
  "url": "https://www.france24.com/en/europe/20260722-fast-moving-wildfire-forces-hundreds-of-evacuations-in-southern-france"
}
```

**Returns:**
- `title`: Article headline
- `summary`: Article summary/chapo
- `description`: Meta description
- `content`: Full article body text
- `date_info`: Publication date information
- `published_date`: Extracted publication date
- `tags`: Article tags (if available)
- `section`: Article section/category
- `word_count`: Approximate word count
- `url`: Original URL

### get_section

Fetch latest articles from a France24 section page.

**Parameters:**
- `section` (required): Section path (e.g., 'france', 'europe', 'africa', 'middle-east', 'americas', 'asia-pacific')

**Example:**
```
{
  "function": "get_section",
  "section": "france"
}
```

**Returns:**
- `title`: Section title
- `description`: Section description
- `articles`: List of articles with URL and title
- `article_count`: Number of articles found
- `url`: Section URL

## Notes

- France24.com blocks direct HTTP requests (returns 403), so this skill uses browser automation
- Article URLs typically contain a date pattern like `/20260722-` in the URL path
- The skill automatically handles cookie consent banners by waiting for page load
- If an article returns 404, it may have been removed or the URL is incorrect

## Common Sections

- `france` - French news
- `europe` - European news
- `africa` - African news
- `middle-east` - Middle East news
- `americas` - Americas news
- `asia-pacific` - Asia-Pacific news
- `business` - Business news
- `sport` - Sports news
- `culture` - Culture news
- `science` - Science news
