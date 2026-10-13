# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# histclo.com Access Skill

This skill extracts structured content from historical essays on the Historical Clothing website (histclo.com), a site containing extensive essays on historical topics including World War II, children's clothing history, and country-specific historical information.

## Site Structure

histclo.com uses a distinctive essay format with:
- A main heading (H1) containing the essay title
- Multiple sections marked by H2 headings
- Paragraphs of content following each H2
- Occasional tables with images and captions
- Navigation links at the bottom of each page

## Functions

### get_essay

Fetches and parses a single essay page, extracting:

- **title**: The main H1 heading
- **page_title**: The browser title
- **introduction**: Content between the H1 and first H2
- **sections**: Array of sections, each with:
  - title: The H2 heading text
  - content: Array of paragraphs (if include_full_content=true)
  - preview: First paragraph preview (if include_full_content=false)
  - paragraph_count: Number of paragraphs
- **images**: Array of images with URL, alt text, and captions
- **related_links**: Navigation links to related pages

**Parameters:**
- `url` (required): Full URL of the essay page
- `include_images` (optional, default: true): Include image information
- `include_full_content` (optional, default: true): Include full paragraph text

**Example:**
```json
{
  "function": "get_essay",
  "url": "https://histclo.com/essay/war/ww2/camp/pac/cbi/burma/cbi-bur42.html"
}
```

### search_essays

Searches for essays by keyword, exploring known topic areas:

**Parameters:**
- `keyword` (required): Search keyword
- `topic_area` (optional): Topic area to search - one of:
  - `ww2`: World War II essays (default)
  - `children`: Children's history essays
  - `country`: Country-specific essays
  - `chron`: Chronological essays

**Example:**
```json
{
  "function": "search_essays",
  "keyword": "burma",
  "topic_area": "ww2"
}
```

## Known URL Patterns

The site organizes essays under several paths:
- `/essay/war/ww2/...` - World War II essays
- `/essay/war/ww2/camp/pac/...` - Pacific campaign
- `/essay/war/ww2/cou/...` - Countries in WWII
- `/country/...` - Country-specific history
- `/chron/...` - Chronological essays

## Notes

- The site uses plain HTML without JavaScript rendering
- Navigation sections are automatically excluded from content extraction
- The extractor handles malformed HTML gracefully
- Image URLs are converted to absolute URLs
- Related links are extracted from the navigation section at the bottom of each page
