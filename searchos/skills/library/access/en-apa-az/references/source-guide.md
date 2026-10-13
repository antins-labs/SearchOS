# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# APA News Agency (en.apa.az) Access Skill

This skill provides access to APA News Agency's English edition news website, enabling retrieval of news articles, category-based news listings, and article search.

## Features

### 1. Get Article (`get_article`)
Retrieve detailed content of a specific news article by its URL.

**Parameters:**
- `url` (required): Full article URL from en.apa.az

**Returns:**
- Article ID, title, category, publication date
- Full article content
- Related articles

**Example:**
```python
params = {
    'function': 'get_article',
    'url': 'https://en.apa.az/foreign-policy/Countries-which-Azerbaijan-established-diplomatic-relations-with-named-304245'
}
```

### 2. Get Latest News (`get_latest_news`)
Retrieve the latest news articles from the homepage or a specific category.

**Parameters:**
- `category` (optional): News category slug
- `page` (optional): Page number for pagination (default: 1)

**Available Categories:**
- `foreign-policy` - Foreign policy news
- `political` - Political news
- `official-news` - Official government news
- `media` - Media news
- `america` - Americas region news
- `europe` - European news
- `asia` - Asian news
- `cis-countries` - CIS countries news
- `economy` - Economic news
- `energy-and-industry` - Energy and industry news
- `finance` - Financial news
- `sport` - Sports news
- `culture` - Culture and arts news
- `social` - Social news
- `incident` - Incident/crime news
- `science-and-education` - Science and education news
- `cryptocurrency` - Cryptocurrency news
- `analysis` - Analysis and opinion
- `blog` - Blog posts

**Returns:**
- List of news items with ID, URL, title, and category

**Example:**
```python
params = {
    'function': 'get_latest_news',
    'category': 'foreign-policy',
    'page': 1
}
```

### 3. Search News (`search_news`)
Search for news articles by keyword.

**Parameters:**
- `query` (required): Search keyword

**Returns:**
- List of matching news articles

**Example:**
```python
params = {
    'function': 'search_news',
    'query': 'Azerbaijan diplomatic relations'
}
```

## Response Format

All functions return a dictionary with the following structure:

### Article Response
```json
{
    "id": "304245",
    "url": "https://en.apa.az/...",
    "title": "Article Title",
    "category": "Foreign Policy",
    "date": "03 January 2020 13:04 (UTC +04:00)",
    "content": "Full article content...",
    "content_preview": "First 500 characters...",
    "related_articles": [
        {"title": "Related Article", "url": "https://..."}
    ]
}
```

### News List Response
```json
{
    "category": "foreign-policy",
    "page": 1,
    "url": "https://en.apa.az/foreign-policy",
    "total": 25,
    "items": [
        {
            "id": "517123",
            "url": "https://en.apa.az/...",
            "title": "Article Title",
            "category": "Foreign Policy"
        }
    ]
}
```

### Error Response
```json
{
    "error": "Error description",
    "url": "requested URL (if applicable)"
}
```

## Notes

- Article URLs must be from the `en.apa.az` domain
- Content is extracted from the main article container, excluding navigation and footer elements
- Date extraction uses pattern matching for the site's date format
- Related articles are limited to 5 items
- News lists are limited to 30 items per request
