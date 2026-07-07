# CCTV News (news.cctv.com) Access Skill

This skill provides programmatic access to CCTV News (央视网新闻) content, including standard news articles and special topic/feature pages.

## Features

### 1. Article Content Extraction (`fetch_article`)
Extracts full content from CCTV news articles including:
- Article title and metadata (author, publish date, keywords)
- Full article text paragraphs
- Article description/summary
- Content length statistics

**Example Usage:**
```python
result = await execute({
    "function": "fetch_article",
    "url": "https://news.cctv.com/2026/06/21/ARTIfijga2NsiX2aPmT87RwX260621.shtml"
})
```

**Returns:**
```json
{
  "success": true,
  "url": "https://news.cctv.com/...",
  "title": "文章标题",
  "author": "作者名",
  "keywords": "关键词",
  "description": "文章摘要",
  "publish_date": "发布日期",
  "content": ["段落1", "段落2", ...],
  "paragraphs": ["文本段落列表"],
  "content_length": 1234
}
```

### 2. Special Topic Page Extraction (`fetch_special_page`)
Extracts content from CCTV special topic pages (专题页面) including:
- Page title and metadata
- Sectioned content
- Full text content
- Images with alt text

**Example Usage:**
```python
result = await execute({
    "function": "fetch_special_page",
    "url": "https://news.cctv.com/special/gdzg2021/syPAGEA3BHYvYOUoOLJXa11wbt220115/"
})
```

**Returns:**
```json
{
  "success": true,
  "url": "https://news.cctv.com/special/...",
  "title": "专题标题",
  "keywords": "关键词",
  "description": "专题描述",
  "sections": [{"id": "content", "paragraphs": [...]}],
  "content": ["文本内容列表"],
  "images": [{"alt": "图片说明", "src": "图片URL"}],
  "content_length": 5678
}
```

### 3. Homepage Article Search (`search_articles`)
Discovers article links from the CCTV News homepage:
- Returns list of current article URLs
- Includes article titles when available
- Configurable maximum number of results

**Example Usage:**
```python
result = await execute({
    "function": "search_articles",
    "max_articles": 10
})
```

**Returns:**
```json
{
  "success": true,
  "total": 10,
  "articles": [
    {
      "url": "https://news.cctv.com/2026/06/21/ARTI...",
      "title": "文章标题"
    }
  ]
}
```

### 4. Metadata Extraction (`extract_metadata`)
Extracts only metadata from a page (faster, less data transfer):
- Title, author, keywords, description
- Publish date
- Open Graph metadata

**Example Usage:**
```python
result = await execute({
    "function": "extract_metadata",
    "url": "https://news.cctv.com/2026/06/21/ARTI..."
})
```

## Technical Details

### Content Extraction Strategy

The skill uses multiple extraction methods to handle CCTV's different page layouts:

1. **Article Pages**: 
   - Extracts content from JavaScript `contentdate` variables in the HTML
   - Falls back to text node extraction with filtering
   - Identifies and removes navigation, UI elements, and scripts

2. **Special Topic Pages**:
   - Searches for content divs with standard IDs
   - Extracts all meaningful Chinese text content
   - Captures images with descriptive alt text

3. **Text Filtering**:
   - Filters out JavaScript code and UI elements
   - Requires minimum Chinese character ratio (30%) to avoid code fragments
   - Minimum line length threshold (30 characters)

### URL Patterns

- **News Articles**: `https://news.cctv.com/YYYY/MM/DD/ARTI*.shtml`
- **Special Topics**: `https://news.cctv.com/special/*/PAGE*.shtml` or similar patterns
- **Homepage**: `https://news.cctv.com`

### Error Handling

All functions return structured error responses:
```json
{
  "success": false,
  "error": "Error description",
  "url": "requested_url"
}
```

Common errors:
- `HTTP 404`: Page not found
- `Missing required parameter: url`: URL parameter not provided
- `URL must be from news.cctv.com domain`: Invalid domain
- `Request timeout`: Request took too long

## Implementation Notes

### Why Direct HTTP Instead of Browser Automation?

The skill uses direct HTTP requests (via `aiohttp`) instead of browser automation because:

1. CCTV pages serve all content in the HTML response
2. Content is accessible without JavaScript execution
3. Direct HTTP is significantly faster and more reliable
4. Reduced resource usage and complexity

### Handling of Security Features

CCTV implements some anti-scraping measures, but they primarily affect:
- Dynamic content loading (which doesn't impact our extraction)
- Rate limiting (manageable with reasonable request patterns)

The skill successfully extracts content by:
- Parsing the static HTML response
- Extracting embedded content from JavaScript variables
- Using appropriate User-Agent headers

## Limitations

1. **Video Content**: The skill extracts text content but does not download or transcribe videos
2. **Rate Limiting**: High request volumes may trigger rate limiting - use responsibly
3. **Dynamic Content**: Some highly dynamic features may not be captured
4. **Image URLs**: Some image URLs use relative paths (automatically converted to absolute)

## Testing

Test all functions with the built-in test:
```bash
python executor.py
```

This will demonstrate:
- Article extraction from a real news article
- Special topic page extraction
- Homepage article discovery