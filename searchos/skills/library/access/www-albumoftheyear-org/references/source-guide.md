# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Album of the Year Access Skill

This skill fetches album lists and ratings from [Album of the Year](https://www.albumoftheyear.org) user list pages.

## ⚠️ Important Limitations

**Cloudflare Bot Protection**: Album of the Year uses aggressive Cloudflare bot protection that actively blocks automated access. This skill implements anti-detection measures, but **access may fail** due to the site's security measures.

If the skill reports `blocked_by_cloudflare: true`, the site has blocked the automated request. In this case:
- Try accessing the URL directly in a web browser
- The site may allow access after completing a CAPTCHA challenge manually
- Consider using alternative data sources if available

## Supported Functions

### `get_list`
Fetches a user's album list page.

**Parameters:**
- `url` (required): Full URL to the album list page
  - Example: `https://www.albumoftheyear.org/user/fnftokyodrift/list/127650/riaa-diamond-certified-albums/`
- `wait_time` (optional): Maximum seconds to wait for Cloudflare challenge (default: 30)

**Example:**
```json
{
  "function": "get_list",
  "url": "https://www.albumoftheyear.org/user/fnftokyodrift/list/127650/riaa-diamond-certified-albums/",
  "wait_time": 45
}
```

### `get_user`
Fetches a user's profile page.

**Parameters:**
- `url` (required): Full URL to the user profile page
  - Example: `https://www.albumoftheyear.org/user/fnftokyodrift/`
- `wait_time` (optional): Maximum seconds to wait for Cloudflare challenge (default: 30)

**Example:**
```json
{
  "function": "get_user",
  "url": "https://www.albumoftheyear.org/user/fnftokyodrift/"
}
```

## Return Values

### Success
```json
{
  "success": true,
  "blocked_by_cloudflare": false,
  "data": {
    "url": "...",
    "title": "Page Title",
    "body_text": "Full page text content...",
    "albums": [
      {"name": "Album Name", "url": "https://..."}
    ],
    "content_length": 12345
  }
}
```

### Cloudflare Block
```json
{
  "success": false,
  "blocked_by_cloudflare": true,
  "error": "Cloudflare bot protection blocked access...",
  "url": "..."
}
```

### Error
```json
{
  "success": false,
  "blocked_by_cloudflare": false,
  "error": "Error description..."
}
```

## Data Available on Album of the Year

When access is successful, the following data may be available from user lists:

- **Album names** and links to album pages
- **Artist information** and links to artist pages
- **User ratings** (if displayed on the list)
- **Release information** (year, label, etc.)
- **Certification data** (for lists tracking RIAA certifications)
- **User comments** and list descriptions

## Typical Use Cases

1. **RIAA Diamond Certified Albums Lists**: Users create lists tracking diamond-certified albums
2. **Personal Collection Lists**: Users' rated albums and favorites
3. **Genre/Year Lists**: Curated lists by genre, year, or theme
4. **Rating Analysis**: Aggregate user ratings and reviews

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `blocked_by_cloudflare: true` | Access the URL manually in a browser |
| Navigation timeout | Increase `wait_time` parameter |
| Empty album list | Page may not have loaded fully; try increasing wait time |
| Invalid URL error | Ensure URL is from albumoftheyear.org domain |

## Technical Notes

- Uses Chromium-based browser automation via Playwright
- Implements anti-detection measures (user agent spoofing, webdriver hiding)
- Waits for Cloudflare challenge to complete before extracting data
- Extracts album links and basic page structure when accessible
