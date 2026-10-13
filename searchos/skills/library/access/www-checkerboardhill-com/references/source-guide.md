# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Checkerboard Hill - Hong Kong MTR Tunnels Access Skill

This skill fetches structured information about Hong Kong MTR underwater tunnels and related transport articles from [Checkerboard Hill](https://www.checkerboardhill.com), a blog by Marcus Wong covering Hong Kong transport infrastructure, tourism, and everyday life.

## Overview

Checkerboard Hill is a detailed blog documenting Hong Kong's transport infrastructure, including the Mass Transit Railway (MTR) system. The site contains in-depth technical articles about railway tunnels, stations, rolling stock, and infrastructure projects.

## Available Functions

### `get_tunnel_summary`

Extracts structured information about the four MTR underwater tunnels crossing Victoria Harbour:

- **MTR Cross-Harbour Tunnel** (Tsuen Wan Line)
- **Eastern Harbour Crossing** (Tseung Kwan O Line)
- **Western Immersed Tube** (Airport Express / Tung Chung Line)
- **Shatin to Central Link Cross Harbour Tunnels** (North South Corridor)

For each tunnel, returns:
- Full name and contract number
- Location (start and end points)
- Railway line and stations
- What it carries (tracks, road lanes, etc.)
- Construction dates (commenced, completed)
- Type of construction (immersed tube, etc.)
- Dimensions (length, width, height, depth)
- Technical description and construction details

**Parameters:**
- `url` (optional): Article URL. Defaults to the main underwater tunnels article.

**Example:**
```json
{
  "function": "get_tunnel_summary"
}
```

### `get_article`

Fetches and parses a single article from Checkerboard Hill with full content extraction.

**Parameters:**
- `url` (required): The article URL to fetch

**Returns:**
- Title, author, publish date
- Full article content (paragraphs)
- Headings structure
- Images with alt text
- Related links
- Tags and categories
- Word count

**Example:**
```json
{
  "function": "get_article",
  "url": "https://www.checkerboardhill.com/2020/03/mtr-cross-harbour-tunnel-flood-gates/"
}
```

### `search_posts`

Searches for articles on Checkerboard Hill by keyword.

**Parameters:**
- `query` (required): Search keywords

**Returns:**
- List of matching articles with titles and URLs
- Result count

**Example:**
```json
{
  "function": "search_posts",
  "query": "immersed tube"
}
```

### `list_mtr_posts`

Lists posts tagged with "MTR" on Checkerboard Hill.

**Parameters:**
- `page` (optional): Page number, defaults to 1

**Returns:**
- List of MTR-related posts with titles and URLs
- Pagination info (has_next_page, has_previous_page)

**Example:**
```json
{
  "function": "list_mtr_posts",
  "page": 1
}
```

## Key Content Available

The site contains detailed technical articles about:

- **MTR Underwater Tunnels**: Comprehensive specifications of all four cross-harbour railway tunnels
- **Tunnel Infrastructure**: Flood gates, ventilation shafts, construction methods
- **MTR Depots**: Ho Tung Lau Depot and other facilities
- **Rolling Stock**: Train orders, retro liveries, new equipment
- **Related Infrastructure**: Hong Kong-Zhuhai-Macao Bridge, road tunnels

## Data Structure

Tunnel specifications are extracted from structured paragraphs in the article format:

```
Full name: [contract name]
Location: [start] to [end]
Railway: [line], between [stations]
Carries: [tracks/lanes]
Commenced: [date]
Completed: [date]
Type: [construction type]
Length: [dimension]
Width: [dimension]
Height: [dimension]
Depth: [dimension]
```

## Technical Notes

- The site is a WordPress blog with standard HTML structure
- Content is accessible via direct HTTP requests (no JavaScript rendering required)
- Article content is in `<article>` or `.entry-content` elements
- Tunnel specifications are in paragraph text with key: value format
- No authentication or special headers required
- Rate limiting: Be respectful of the server; avoid rapid successive requests

## Related Articles

Some useful article URLs for reference:

- Main tunnel article: `/2017/05/underwater-tunnels-mass-transit-railway-hong-hong/`
- Flood gates: `/2020/03/mtr-cross-harbour-tunnel-flood-gates/`
- Ventilation shafts: `/2021/07/ventilation-shafts-across-the-mtr-network/`
- Ho Tung Lau Depot: `/2025/02/history-mtr-ho-tung-lau-depot/`

## Author

Checkerboard Hill is authored by Marcus Wong, documenting Hong Kong's transport infrastructure with detailed technical information and historical context.
