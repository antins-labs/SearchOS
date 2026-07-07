# Sohu Article Fetcher - SearchOS Access Skill

Fetches article content and extracts rankings from Sohu.com travel ranking articles.

## Overview

This skill accesses Sohu.com article pages, specifically designed for travel ranking articles that contain "Top 50" style lists. It extracts:

- Article metadata (title, publish time, author)
- Full article content
- Structured ranking data (Top N lists, individual rank mentions)

## Supported URLs

Works with Sohu article URLs in the format:
- `https://www.sohu.com/a/{article_id}_{media_id}`

Example:
- `https://www.sohu.com/a/748417406_484968` - 2023 Top 50 Natural Water Scenic Areas
- `https://www.sohu.com/a/629022385_484968` - 2022 Top 50 Natural Water Scenic Areas  
- `https://www.sohu.com/a/629021039_484968` - 2022 Top 50 Historical Sites

## Functions

### fetch_article

Fetches and parses a single Sohu article.

**Parameters:**
- `url` (string, optional): Full article URL
- `article_id` (string, optional): Article ID (requires media_id)
- `media_id` (string, optional): Media/author ID
- `extract_rankings` (boolean, default: true): Whether to extract ranking information

**Returns:**
- `success`: Boolean status
- `title`: Article title
- `publish_time`: Publication date/time
- `description`: Meta description
- `content`: Full article text
- `content_length`: Character count
- `paragraph_count`: Number of paragraphs
- `rankings`: Extracted ranking data (if available)

**Example:**
```python
result = await execute({
    "function": "fetch_article",
    "url": "https://www.sohu.com/a/748417406_484968"
})
```

### search_articles

Not supported - Sohu does not provide a public search API. Use direct article URLs.

## Ranking Extraction

The skill automatically extracts various ranking formats:

### Top N Lists
Extracts lists like "排名前十的自然亲水类景区分别为九寨沟、西湖、喀纳斯..."
```json
{
  "type": "top_n_list",
  "n": 10,
  "title": "Top 10",
  "items": ["九寨沟", "西湖", "喀纳斯", ...]
}
```

### Individual Rank Mentions
Extracts mentions like "排名第六的天目湖旅游度假区..."
```json
{
  "type": "rank_mentions",
  "items": [
    {"rank": 1, "name": "九寨沟"},
    {"rank": 6, "name": "天目湖"},
    ...
  ]
}
```

### Numbered Lists
Extracts paragraphs starting with numbers.

## Technical Details

- Uses direct HTTP requests (httpx) - no browser automation required
- Extracts content from `<article id="mp-editor">` element
- Parses Chinese text for ranking patterns
- Handles encoding and HTML entity cleanup
- Follows redirects automatically

## Error Handling

Returns structured error objects:
- `{"success": false, "error": "Missing required parameter: url or article_id"}`
- `{"success": false, "error": "HTTP 404"}`
- `{"success": false, "error": "Request timeout"}`

## Use Cases

1. **Travel Research**: Extract ranked lists of tourist attractions
2. **Content Analysis**: Analyze Sohu travel articles for trends
3. **Data Collection**: Build databases of Chinese scenic area rankings
4. **Monitoring**: Track changes in rankings over time

## Notes

- Articles are in Chinese (Simplified)
- Ranking extraction optimized for Sohu travel ranking articles
- Some articles may not contain structured rankings
- Media ID (the number after underscore) often indicates the source account