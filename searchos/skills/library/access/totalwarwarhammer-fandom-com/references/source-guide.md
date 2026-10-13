# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Total War: Warhammer Fandom Wiki Access Skill

This skill retrieves structured information from the Total War: Warhammer Fandom wiki (totalwarwarhammer.fandom.com) using the MediaWiki API.

## Overview

The site is protected by Cloudflare which blocks direct HTTP requests and standard browser automation. This skill bypasses that protection by using the MediaWiki API endpoint which is publicly accessible without rate limiting or bot detection.

## Available Functions

### get_page
Fetch a wiki page with complete structured data.

**Parameters:**
- `page_title` (required): The wiki page title (e.g., "Ogre Kingdoms", "The Realm of Chaos")
- `include_html` (optional, default: true): Whether to parse HTML for infobox, sections, and tables

**Returns:**
- `title`: The canonical page title
- `exists`: Whether the page exists
- `infobox`: Structured data extracted from the page's infobox template
- `sections`: List of sections with titles and content
- `tables`: List of tables extracted from the page
- `wikitext`: Raw wikitext source
- `links`: List of internal links on the page
- `categories`: List of categories the page belongs to

**Example:**
```json
{
  "function": "get_page",
  "page_title": "Ogre Kingdoms"
}
```

### search
Search for wiki pages matching a query.

**Parameters:**
- `query` (required): Search query string
- `limit` (optional, default: 10): Maximum number of results

**Returns:**
- `query`: The search query
- `total`: Number of results
- `results`: List of matching pages with title, snippet, word count, and timestamp

**Example:**
```json
{
  "function": "search",
  "query": "Khorne",
  "limit": 20
}
```

### get_category
Get all pages in a category.

**Parameters:**
- `category` (required): Category name (with or without "Category:" prefix)
- `limit` (optional, default: 50): Maximum number of results

**Returns:**
- `category`: The category name
- `total`: Number of pages
- `members`: List of page titles and IDs

**Example:**
```json
{
  "function": "get_category",
  "category": "Races"
}
```

### get_page_links
Get all internal links from a page.

**Parameters:**
- `page_title` (required): The wiki page title

**Returns:**
- `title`: Page title
- `links`: List of linked page titles

**Example:**
```json
{
  "function": "get_page_links",
  "page_title": "Ogre Kingdoms"
}
```

### get_backlinks
Get all pages that link to a specific page.

**Parameters:**
- `page_title` (required): The wiki page title
- `limit` (optional, default: 50): Maximum number of results

**Returns:**
- `title`: Page title
- `total`: Number of backlinks
- `backlinks`: List of linking pages

**Example:**
```json
{
  "function": "get_backlinks",
  "page_title": "Greasus Goldtooth"
}
```

### get_all_pages
Get a list of all wiki pages (for discovery).

**Parameters:**
- `limit` (optional, default: 100): Maximum number of results

**Returns:**
- `total`: Number of pages
- `pages`: List of page titles and IDs

## Data Extraction

The skill extracts:
- **Infobox data**: Key-value pairs from Fandom's portable infobox templates (e.g., faction type, campaigns, legendary lords, climates, etc.)
- **Sections**: Page content organized by section headings
- **Tables**: Wiki tables with headers and rows
- **Categories**: Wiki categories the page belongs to
- **Links**: Internal wiki links

## Common Use Cases

1. **Get faction/race information**: Retrieve infobox data for playable factions
2. **Get unit information**: Extract unit stats and abilities
3. **Explore campaign mechanics**: Read about game mechanics and campaigns
4. **Find related content**: Use links and backlinks to discover related pages
5. **Browse categories**: Get all pages in categories like "Races", "Units", "Legendary Lords"

## Notes

- The MediaWiki API is stable and well-documented
- No rate limiting has been observed, but use reasonable limits
- Page titles are case-sensitive but the API normalizes them
- Redirects are automatically followed
- The wikitext source is always included; HTML parsing is optional
