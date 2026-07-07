# CIH Index Report Access Skill

## Overview

This skill provides access to TOP50 ranking reports from **m.cih-index.com** (CIH指数), a Chinese real estate and property management data platform operated by 中国指数研究院 (China Index Academy).

The platform hosts monthly reports on property management companies, including:
- 新增合约面积TOP50 (New Contract Area TOP50)
- 品牌传播榜单 (Brand Communication Rankings)
- Other property management industry rankings

## Data Structure

Reports on this site are served as **paginated images** rather than text content. Each report page is a separate JPG image that requires:
1. A valid `wsSecret` and `wsTime` token (obtained via the `/wy/report/getToken` API)
2. The base URL from the report metadata
3. The page number (1-indexed)

The HTML page embeds initial state JSON with report metadata including:
- Report title
- Publication date
- Total page count
- Visit statistics
- Tags/categories
- Base URL for images

## Functions

### get_report

Fetches comprehensive metadata for a report.

**Parameters:**
- `report_id` (required): The numeric report ID (e.g., "100275", "100276")
- `include_image_urls` (optional): Set to `true` to also generate signed URLs for all report pages

**Returns:**
```json
{
  "success": true,
  "report_id": "100276",
  "title": "2025年4月中国物业服务企业新增合约面积TOP50",
  "add_time": "2025-06-04",
  "page_count": 8,
  "visit_count": 9604,
  "tags": ["物业月报"],
  "base_url": "https://cihcdnzip.soufunimg.com/backend/reportCreisFile/100276/b288ef92ab724ac78b7a36cfbfcd44ec",
  "csrf": "...",
  "image_urls": [...]  // Only if include_image_urls=true
}
```

### get_page_image

Generates a signed URL for a specific report page.

**Parameters:**
- `report_id` (required): The numeric report ID
- `page_number` (required): Page number (1-indexed)
- `width` (optional): Image width in pixels (default: 1278)

**Returns:**
```json
{
  "success": true,
  "url": "https://cihcdnzip.soufunimg.com/backend/reportCreisFile/100276/..._1.jpg?op=imageView2&mode=2&wsSecret=...&wsTime=...&width=1278",
  "content_type": "image/jpeg",
  "content_length": "151812"
}
```

## Usage Examples

### Get report metadata only
```python
params = {
    "function": "get_report",
    "report_id": "100276"
}
```

### Get report with all page URLs
```python
params = {
    "function": "get_report",
    "report_id": "100276",
    "include_image_urls": True
}
```

### Get specific page image URL
```python
params = {
    "function": "get_page_image",
    "report_id": "100276",
    "page_number": 1,
    "width": 1920  # Optional, defaults to 1278
}
```

## Technical Details

### Authentication Flow

1. **Initial Page Load**: Fetch the HTML page which contains:
   - `window.__INITIAL_STATE__` object with report metadata and CSRF token
   - The base URL for report images (without page number or signature)

2. **Token Generation**: Call `/wy/report/getToken` with:
   - CSRF token from the initial state
   - Referer parameter
   - Request transaction UUID

3. **Image URL Construction**: Build the full URL:
   ```
   {base_url}_{page_number}.jpg?op=imageView2&mode=2&wsSecret={secret}&wsTime={time}&width={width}
   ```

### Limitations

- Reports are delivered as images, not structured text data
- OCR may be required to extract text content from images
- Tokens have expiration times and are tied to the request session
- Image URLs require specific headers (User-Agent, Referer) for access

### Error Handling

The skill returns structured error responses for:
- Invalid or missing report IDs
- Network failures
- Token generation failures
- Invalid page numbers
- Expired or invalid tokens

## Common Report IDs

Based on the probe data:
- `100275`: 2025年4月-中国物业服务企业品牌传播榜单 (Brand Communication Rankings)
- `100276`: 2025年4月中国物业服务企业新增合约面积TOP50 (New Contract Area TOP50)

Report IDs increment monthly and are typically in the 100XXX range.