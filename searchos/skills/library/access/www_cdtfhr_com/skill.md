# CDTFHR (天府菁英网) Job Announcements Access Skill

## Overview

This skill provides access to job recruitment announcements from the **Tianfu Elite Network (天府菁英网)** at www.cdtfhr.com. The site is a dedicated job board for government and public sector positions in the Chengdu Tianfu New Area and surrounding regions in Sichuan Province, China.

## Website Information

- **Website**: https://www.cdtfhr.com
- **API Base**: https://api.cdtfhr.com
- **Main Endpoint**: `/v1/web/exam/announce` (POST)
- **Content Types**: Recruitment announcements (招聘公告), hiring notices, examination schedules, candidate lists

## Available Functions

### 1. `list_announcements`

List job announcements with pagination support.

**Parameters:**
- `page` (optional, integer, default=1): Page number starting from 1

**Example:**
```python
result = await execute({
    "function": "list_announcements",
    "page": 1
})
```

**Returns:**
```json
{
  "success": true,
  "announcements": [
    {
      "id": 1487,
      "exam_id": 261,
      "title": "松潘县总工会2026年公开招聘工作人员的公告",
      "name": "招聘公告",
      "release_time": "2026/06/08",
      "hits": 1110,
      "content_preview": "...",
      "content_full": "Full HTML content..."
    }
  ],
  "pagination": {
    "total": 1418,
    "count": 10,
    "per_page": 10,
    "current_page": 1,
    "total_pages": 142,
    "has_next": true
  }
}
```

### 2. `search_announcements`

Search announcements by keyword.

**Parameters:**
- `keyword` (required, string): Search keyword (e.g., "教师", "公司", "会计")
- `page` (optional, integer, default=1): Page number starting from 1

**Example:**
```python
result = await execute({
    "function": "search_announcements",
    "keyword": "教师",
    "page": 1
})
```

## Data Fields

Each announcement contains:

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique announcement ID |
| `exam_id` | integer | Associated exam ID (can be null) |
| `type` | string | Announcement type (often null) |
| `name` | string | Category name (e.g., "招聘公告", "拟聘公示") |
| `title` | string | Announcement title |
| `content_preview` | string | First 200 characters of content |
| `content_full` | string | Full HTML content |
| `release_time` | string | Release date (format: YYYY/MM/DD) |
| `hits` | integer | View count |
| `status` | integer | Status flag |
| `icon` | string | Icon URL (if available) |
| `created_at` | string | Creation timestamp |

## Use Cases

- **Job Seekers**: Search for open positions by keywords (职位类型, 地区, 单位名称)
- **Researchers**: Monitor government/public sector hiring trends
- **Analysis**: Track announcement frequency, popular job types, application deadlines

## Notes

1. **Language**: All content is in Chinese (Simplified)
2. **Geographic Focus**: Primarily covers Chengdu Tianfu New Area, Aba Prefecture, and surrounding Sichuan regions
3. **Content Types**: Includes recruitment announcements, exam notices, candidate lists, and hiring results
4. **Pagination**: 10 items per page; use `total_pages` to determine the number of available pages
5. **Freshness**: The API updates regularly with new announcements; check `release_time` for publication dates
6. **Full Content**: The `content_full` field contains HTML markup; use appropriate parsing for clean text extraction

## Technical Details

- **API Method**: POST with JSON payload
- **Authentication**: None required (public API)
- **Rate Limiting**: Not observed in testing, but be respectful of server resources
- **CORS**: API allows cross-origin requests from www.cdtfhr.com

## Error Handling

The skill returns structured errors with the following fields:
- `error`: Human-readable error message
- `error_code`: Machine-readable error code (HTTP_ERROR, API_ERROR, NETWORK_ERROR, INVALID_INPUT, UNKNOWN_FUNCTION)
- `details`: Additional context about the error