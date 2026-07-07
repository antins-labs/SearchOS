# National Health Commission of China (NHC) Access Skill

## Overview

This skill provides programmatic access to the National Health Commission of China website (www.nhc.gov.cn), allowing retrieval of:
- Lists of medical institution announcements and official documents
- Detailed content of specific announcements
- Search results (when available)

## Anti-Bot Protection

**IMPORTANT**: The NHC website uses sophisticated anti-bot protection (likely Ray WAF or similar) that makes direct HTTP requests impossible. The protection includes:

1. **Challenge-based authentication**: Initial requests return HTTP 412 (Precondition Failed)
2. **JavaScript execution required**: A complex obfuscated JavaScript challenge must be executed
3. **HTTP-only cookies**: Two cookies (`5uRo8RWcod0KO`, `5uRo8RWcod0KP`) are set via JavaScript
4. **Browser fingerprinting**: Additional checks beyond standard browser detection

This skill uses **Playwright** with extensive stealth measures and retry logic to bypass this protection.

## Rate Limits

Due to the anti-bot protection and JavaScript execution requirements:
- **Default timeout**: 60 seconds per request
- **Maximum retries**: 3 attempts with exponential backoff
- **Recommended rate**: No more than 10 requests per minute
- **Note**: Each request may take 10-30 seconds due to WAF challenge execution

## Functions

### 1. get_list

Retrieve a paginated list of documents from a category page.

**Parameters:**
| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| url | string | Yes | - | List page URL (e.g., https://www.nhc.gov.cn/wjw/fzszjg/list.shtml) |
| page | integer | No | 1 | Page number to retrieve |
| max_items | integer | No | 50 | Maximum number of items to return |

**Returns:**
```json
{
  "success": true,
  "url": "https://www.nhc.gov.cn/wjw/fzszjg/list.shtml",
  "title": "Page Title",
  "items": [
    {
      "title": "Document Title",
      "url": "https://www.nhc.gov.cn/fys/c100077/202411/xxxxx.shtml",
      "date": "2024-11-15"
    }
  ],
  "total": 15,
  "page": 1,
  "pagination": {
    "pages": [1, 2, 3, 4, 5],
    "has_next": true
  },
  "accessed_at": "2024-01-15T10:30:00"
}
```

**Common List URLs:**
- Medical Institutions: `https://www.nhc.gov.cn/wjw/fzszjg/list.shtml`
- Policy Documents: `https://www.nhc.gov.cn/wjw/zcwj/list.shtml`
- News: `https://www.nhc.gov.cn/xcs/yqfkdt/list.shtml`

### 2. get_detail

Retrieve the full content of a specific document.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| url | string | Yes | Full URL to the document (.shtml page) |

**Returns:**
```json
{
  "success": true,
  "title": "Document Title",
  "content": "Full text content...",
  "content_html": "HTML content...",
  "content_length": 5432,
  "date": "2024-11-15",
  "source": "Health Commission",
  "author": "Author Name",
  "url": "https://www.nhc.gov.cn/fys/c100077/202411/xxxxx.shtml",
  "accessed_at": "2024-01-15T10:30:00"
}
```

### 3. search

Search for documents by keyword (if available).

**Parameters:**
| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| keyword | string | Yes | - | Search keyword |
| category | string | No | null | Category filter |
| max_items | integer | No | 20 | Maximum results |

**Returns:**
```json
{
  "success": true,
  "keyword": "医疗",
  "category": null,
  "results": [
    {
      "title": "Result Title",
      "url": "https://www.nhc.gov.cn/..."
    }
  ],
  "total": 50,
  "search_url": "https://www.nhc.gov.cn/search?...",
  "accessed_at": "2024-01-15T10:30:00"
}
```

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Error message",
  "error_code": "ERROR_CODE",
  "url": "..."
}
```

**Error Codes:**
| Code | Description |
|------|-------------|
| MISSING_FUNCTION | No function specified in params |
| MISSING_URL | Required URL parameter missing |
| MISSING_KEYWORD | Required keyword parameter missing |
| UNKNOWN_FUNCTION | Invalid function name |
| WAF_BLOCKED | Anti-bot protection blocked the request |
| REQUEST_FAILED | Network or browser error |
| NO_SEARCH | Search functionality not available |
| EXECUTION_ERROR | Unexpected error |

## Usage Examples

### Example 1: Get list of medical institution announcements

```python
result = await execute({
    "function": "get_list",
    "url": "https://www.nhc.gov.cn/wjw/fzszjg/list.shtml",
    "page": 1,
    "max_items": 20
})

if result["success"]:
    for item in result["items"]:
        print(f"{item['date']}: {item['title']}")
        print(f"  URL: {item['url']}")
```

### Example 2: Get detailed content

```python
result = await execute({
    "function": "get_detail",
    "url": "https://www.nhc.gov.cn/fys/c100077/202411/xxxxx.shtml"
})

if result["success"]:
    print(f"Title: {result['title']}")
    print(f"Date: {result['date']}")
    print(f"Content: {result['content'][:500]}...")
```

### Example 3: Search (if available)

```python
result = await execute({
    "function": "search",
    "keyword": "医疗机构执业登记",
    "max_items": 10
})

if result["success"]:
    for item in result["results"]:
        print(item["title"])
```

## Technical Details

### Browser Configuration

The skill uses Playwright with:
- **Headless Chromium** browser
- **Stealth scripts** to hide automation markers
- **Custom User-Agent** (Macintosh Chrome 120)
- **Chinese locale** (zh-CN) and timezone (Asia/Shanghai)
- **WebGL spoofing** to appear as real device

### Retry Strategy

Requests use exponential backoff:
1. Initial request (60s timeout)
2. If 412/400: Wait 10s, reload
3. If still blocked: Wait 20s, reload
4. If still blocked: Wait 40s, reload
5. Return error after max retries

### Known Limitations

1. **Intermittent failures**: Even with proper stealth measures, the WAF may still block some requests
2. **Long response times**: First request may take 20-30 seconds due to WAF challenge
3. **Search unavailable**: The search function may not work if the site doesn't have public search
4. **Pagination**: Some list pages may use different pagination patterns

## Troubleshooting

### "WAF_BLOCKED" errors

If you consistently get WAF_BLOCKED errors:
1. Reduce request frequency
2. Wait between requests (recommend 30+ seconds)
3. Try different times of day
4. The WAF may update its detection methods

### "REQUEST_FAILED" errors

Network or browser errors:
1. Check internet connectivity
2. The site may be down or slow
3. Try increasing timeout parameter

### Empty results

If requests succeed but return empty results:
1. The page structure may have changed
2. Different selectors may be needed
3. Content may be loaded dynamically after page load

## Dependencies

- playwright >= 1.40.0
- Python >= 3.8

## Changelog

### v1.0.0 (2024-01-15)
- Initial implementation
- WAF bypass with Playwright stealth
- get_list, get_detail, search functions
- Comprehensive error handling