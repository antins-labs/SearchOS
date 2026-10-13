# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# AllKPop Article Access Skill

Access K-pop news articles from www.allkpop.com.

## Overview

This skill fetches article content and metadata from AllKPop, a popular K-pop news website. It can:
- Retrieve full article content from a specific URL
- Search for articles by keyword
- Extract article metadata (title, author, date, images)

## Important Note

**This site uses aggressive Cloudflare Turnstile protection** that may block automated access. The skill implements:
- Extended waiting periods for challenge completion
- Anti-detection browser configurations
- Multiple content extraction strategies

Success rate depends on Cloudflare's bot detection, which may vary.

## Functions

### fetch_article

Fetch a single article by URL.

**Parameters:**
- `url` (required): The full article URL
- `max_wait_seconds` (optional): Time to wait for Cloudflare challenge (default: 30)

**Example:**
```json
{
  "function": "fetch_article",
  "url": "https://www.allkpop.com/article/2024/03/yg-entertainment-artists-who-founded-their-own-labels",
  "max_wait_seconds": 45
}
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.allkpop.com/article/...",
  "title": "Article Title",
  "content": "Full article text...",
  "author": "Author Name",
  "date": "2024-03-15",
  "images": [
    {"src": "https://...", "alt": "Image description"}
  ],
  "error": null
}
```

### search_articles

Search for articles on AllKPop.

**Parameters:**
- `query` (required): Search keywords
- `max_wait_seconds` (optional): Time to wait for Cloudflare challenge (default: 30)

**Example:**
```json
{
  "function": "search_articles",
  "query": "BTS comeback",
  "max_wait_seconds": 30
}
```

**Returns:**
```json
{
  "success": true,
  "query": "BTS comeback",
  "results": [
    {
      "title": "Article Title",
      "url": "https://www.allkpop.com/article/...",
      "snippet": "Brief preview text..."
    }
  ],
  "error": null
}
```

## Error Handling

When Cloudflare blocks access, the skill returns:
```json
{
  "success": false,
  "error": "Cloudflare challenge did not complete. The site may be blocking automated access.",
  "url": "https://..."
}
```

## Troubleshooting

1. **Cloudflare blocking**: Increase `max_wait_seconds` to 45-60 seconds
2. **No content extracted**: The page structure may have changed
3. **Timeout errors**: The site may be slow or experiencing issues

## Technical Details

- Uses Playwright with Chromium browser
- Implements anti-detection measures (webdriver flag removal, fake plugins, etc.)
- Waits for Cloudflare Turnstile challenge completion
- Falls back through multiple content selectors
- Extracts structured metadata when available
