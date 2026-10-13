# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Madain Project - Egyptian Pyramids Access Skill

This skill fetches structured data about Egyptian pyramids from the [Madain Project](https://madainproject.com) website, a comprehensive resource for Abrahamic history and archaeology.

## Features

### list_egyptian_pyramids
Retrieves the complete list of Egyptian pyramids from the Madain Project database, including:
- Pyramid name and ID
- Date/period of construction
- Thumbnail image URL
- Brief description
- Link to detail page

Returns approximately 21 pyramids with chronological information spanning from the Third Dynasty (circa 2667 BCE) to the Middle Kingdom (circa 1860 BCE).

### get_pyramid_detail
Fetches detailed information about a specific pyramid, including:
- Full title and description
- Photo gallery (up to 10 images)
- Content sections with headings
- Geographic coordinates (when available)

Provide the `slug` parameter which is the URL path component (e.g., `pyramid_of_djoser`, `great_pyramid_of_giza`, `bent_pyramid`).

### search_pyramids
Searches the pyramid list for entries matching a query term. The search is performed against pyramid titles, descriptions, and IDs.

## Data Source

All data is fetched from:
- List page: `https://madainproject.com/list_of_egyptian_pyramids`
- Detail pages: `https://madainproject.com/{slug}`

## Example Usage

```json
// List all pyramids
{"function": "list_egyptian_pyramids"}

// Get details for the Great Pyramid of Giza
{"function": "get_pyramid_detail", "slug": "great_pyramid_of_giza"}

// Search for pyramids at Dahshur
{"function": "search_pyramids", "query": "dahshur"}
```

## Notes

- The Madain Project uses Cloudflare protection; requests include standard browser headers
- Content is in English with some Arabic transliterations for place names
- Images are hosted on the madainproject.com domain
- The site covers pyramids from the Old Kingdom through Middle Kingdom periods
