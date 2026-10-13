# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Japan Experience Museum Listings Access Skill

This skill fetches and parses museum listing pages from www.japan-experience.com, extracting structured information about museums, galleries, and cultural attractions.

## Overview

Japan Experience (www.japan-experience.com) provides comprehensive travel guides for Japan, including detailed museum listings organized by region. This skill extracts structured data from these listing pages, making it easy to discover and explore museums across different Japanese cities and prefectures.

## Features

### Three Main Functions

1. **get_listing** - Extract all museums from a listing page
   - Retrieves complete museum listings with names, descriptions, and links
   - Extracts page metadata (title, publish date, author)
   - Builds table of contents with anchor links
   - Returns count and structured data for each museum

2. **get_museum_detail** - Fetch detailed information about a specific museum
   - Gets full content from individual museum pages
   - Extracts all paragraphs and images
   - Returns metadata and structured content

3. **search_museums** - Search within a listing page
   - Case-insensitive search across museum names and descriptions
   - Returns matching museums with all associated data
   - Shows match count and total museums searched

## Usage Examples

### Get Museum Listing

```json
{
  "function": "get_listing",
  "url": "https://www.japan-experience.com/all-about-japan/nagasaki/museums-and-galleries/nagasaki-museums-listing"
}
```

Returns:
- List of museums with IDs, names, descriptions
- Links to detailed pages
- Associated images
- Page metadata
- Table of contents

### Get Museum Detail

```json
{
  "function": "get_museum_detail",
  "url": "https://www.japan-experience.com/all-about-japan/nagasaki/museums-galleries/nagasaki-bomb-museum"
}
```

Returns:
- Full museum description
- All content paragraphs
- Images with captions
- Page metadata

### Search Museums

```json
{
  "function": "search_museums",
  "url": "https://www.japan-experience.com/all-about-japan/nagasaki/museums-and-galleries/nagasaki-museums-listing",
  "query": "atomic"
}
```

Returns all museums with "atomic" in name or description.

## Data Structure

### Museum Entry

Each museum entry includes:
- `id` - Anchor ID for the section
- `name` - Museum name
- `description` - Primary description paragraph
- `additional_paragraphs` - Any additional text content
- `links` - Related links with text and URLs
- `images` - Associated images with alt text and URLs
- `anchor_url` - Direct link to museum section

### Page Metadata

- `title` - Page heading
- `description` - Meta description
- `publish_date` - Original publication date
- `modified_date` - Last modification date
- `author` - Content author
- `breadcrumbs` - Navigation path

## Technical Details

- Uses direct HTTP requests with aiohttp for efficient fetching
- Parses HTML with BeautifulSoup for reliable extraction
- Handles Japanese and English content
- Validates URLs to ensure they're from japan-experience.com
- Returns structured JSON with success/error status
- No browser automation required (static content)

## Error Handling

The skill returns structured error responses for:
- Invalid or missing parameters
- Non-Japan Experience URLs
- HTTP errors (timeouts, 404s, etc.)
- Empty or malformed responses

All errors include descriptive messages and HTTP status codes where applicable.

## Limitations

- Only works with japan-experience.com URLs
- Requires publicly accessible pages (no authentication)
- Static content only (no JavaScript-rendered content)
- English language pages primarily supported

## Example Output

```json
{
  "success": true,
  "url": "https://www.japan-experience.com/all-about-japan/nagasaki/museums-and-galleries/nagasaki-museums-listing",
  "metadata": {
    "title": "Nagasaki Museums Listing",
    "publish_date": "2015-04-10T15:55:22+0000",
    "modified_date": "2024-10-14T08:45:52+0000",
    "author": "Japan Experience"
  },
  "museum_count": 13,
  "museums": [
    {
      "id": "nmhc",
      "name": "Nagasaki Museum of History and Culture",
      "description": "The Nagasaki Museum of History and Culture introduces the history of Portuguese, Dutch, Korean and Chinese trade with Nagasaki...",
      "links": [...],
      "images": [...],
      "anchor_url": "https://www.japan-experience.com/all-about-japan/nagasaki/museums-and-galleries/nagasaki-museums-listing#nmhc"
    }
  ]
}
```
