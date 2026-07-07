# CNSA Article Extractor

Extracts full article content from the China National Space Administration (CNSA) website at www.cnsa.gov.cn.

## Overview

The CNSA website uses a specific HTML structure for news articles that generic extractors often fail to parse correctly. This skill handles the specific page structure with classes like:

- `.wz_title` - Article title
- `.wz_rq` - Publish date (发布时间)
- `.wz_ly` - Source (来源)
- `.wz_conten` - Main article content

## Functions

### fetch_article

Fetches and parses a single CNSA news article.

**Parameters:**
- `url` (required): Full URL to the CNSA article page

**Returns:**
```json
{
  "url": "https://www.cnsa.gov.cn/n6758823/n6758838/c10726362/content.html",
  "title": "神舟二十号飞船安全顺利返回东风着陆场",
  "publish_date": "2026-01-19",
  "source": "中国载人航天工程网",
  "content": "北京时间2026年1月19日9时34分，神舟二十号飞船返回舱在东风着陆场成功着陆...",
  "keywords": "国家航天局",
  "description": null
}
```

**Error Responses:**
- `NOT_FOUND`: Article page returns 404
- `HTTP_ERROR`: Failed to fetch page (includes status code)
- `TIMEOUT`: Request timed out
- `REQUEST_ERROR`: Network or connection error
- `PARSE_ERROR`: Failed to parse HTML content
- `MISSING_PARAM`: Required URL parameter missing
- `INVALID_URL`: URL format invalid

## Example Usage

```python
result = await execute({
    'function': 'fetch_article',
    'url': 'https://www.cnsa.gov.cn/n6758823/n6758838/c10726362/content.html'
})

if 'error' not in result:
    print(f"Title: {result['title']}")
    print(f"Date: {result['publish_date']}")
    print(f"Source: {result['source']}")
    print(f"Content: {result['content'][:200]}...")
```

## Technical Details

- Uses httpx for HTTP requests with browser-like headers
- Parses HTML with BeautifulSoup4
- Extracts content from paragraphs styled with `text-indent` for proper formatting
- Deduplicates paragraph content
- Removes UI elements (font size controls, print buttons)
- Returns clean, structured article data

## Content Structure Notes

CNSA articles typically follow this structure:

```html
<div class="wz">
  <div class="wz_title">Article Title</div>
  <div class="wz_rqly">
    <span class="wz_rq">发布时间：2026-01-19</span>
    <span class="wz_ly">来源：Source Name</span>
  </div>
  <div class="wz_conten">
    <!-- Paragraphs with text-indent style -->
    <div style="text-indent: 2em; ...">First paragraph...</div>
    <div style="text-indent: 2em; ...">Second paragraph...</div>
  </div>
</div>
```

The extractor handles this specific structure to reliably extract all article components.