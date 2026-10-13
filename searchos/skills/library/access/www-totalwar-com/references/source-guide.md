# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Total War Official Site Access Skill

Extracts patch notes, DLC details, and game information from the official Total War website (www.totalwar.com).

## Overview

The Total War official website uses Next.js with streaming server-side rendering and is protected by Vercel security checkpoint. This skill bypasses the browser-based security challenge by using direct HTTP requests and decoding the embedded Next.js streaming content.

## Functions

### get_patch_notes

Retrieves patch notes and update articles from Total War news URLs.

**Parameters:**
- `url` (required): Full URL to a patch notes article (e.g., `https://www.totalwar.com/news/total-war-warhammer-iii-update-210`)

**Returns:**
- `title`: Article title
- `version`: Patch version number (if detected in title)
- `headings`: List of section headings with levels
- `content`: List of paragraph text content
- `list_items`: List of bullet point items (patch changes)
- `sections`: Grouped changes by section (if detected)
- `images`: List of images with URLs and alt text
- `links`: List of related links
- `meta`: Open Graph and meta data

### get_dlc_info

Retrieves DLC (Downloadable Content) information from game DLC pages.

**Parameters:**
- `url` (required): Full URL to a DLC page (e.g., `https://www.totalwar.com/games/total-war-warhammer-iii/total-war-warhammer-iii-thrones-of-decay`)

**Returns:**
- `title`: DLC name
- `characters`: List of legendary lords/characters with descriptions
- `headings`: Section headings
- `content`: Description paragraphs
- `images`: Images with URLs and alt text
- `links`: Related links
- `meta`: Open Graph and meta data

### get_game_info

Retrieves game information from main game pages.

**Parameters:**
- `url` (required): Full URL to a game page (e.g., `https://www.totalwar.com/games/total-war-warhammer-iii/`)

**Returns:**
- `title`: Game name
- `headings`: Section headings
- `content`: Description paragraphs
- `images`: Images with URLs and alt text
- `links`: All links from the page
- `dlc_links`: Filtered list of DLC/expansion links (if found)
- `meta`: Open Graph and meta data

## Technical Details

### Content Extraction

The skill uses a specialized approach to extract content:

1. **Direct HTTP Request**: Makes a standard HTTP GET request with browser-like headers
2. **Next.js Chunk Decoding**: The site uses Next.js streaming SSR (`self.__next_f.push()`). The skill decodes these Unicode-escaped chunks
3. **HTML Parsing**: Extracts structured content from the decoded HTML fragments
4. **Filtering**: Removes cookie policy text, UI artifacts, and other noise

### URL Patterns

Common URL patterns on the site:
- Patch notes: `https://www.totalwar.com/news/{game}-update-{version}`
- DLC pages: `https://www.totalwar.com/games/{game}/{game}-{dlc-name}`
- Game pages: `https://www.totalwar.com/games/{game}/`

## Example Usage

```json
{
  "function": "get_patch_notes",
  "url": "https://www.totalwar.com/news/total-war-warhammer-iii-update-210"
}
```

```json
{
  "function": "get_dlc_info",
  "url": "https://www.totalwar.com/games/total-war-warhammer-iii/total-war-warhammer-iii-thrones-of-decay"
}
```

## Limitations

- Only works with www.totalwar.com URLs
- May fail if the site's security measures change significantly
- Content extraction depends on the site's HTML structure remaining consistent
- Some dynamic content loaded via additional API calls may not be captured

## Error Handling

The skill returns structured error responses:
- `{"error": "HTTP 404", "url": "..."}` - Page not found
- `{"error": "Security checkpoint detected", "url": "..."}` - Vercel security challenge
- `{"error": "No content extracted", "url": "..."}` - Failed to parse content
- `{"error": "Missing required parameter: url"}` - Invalid input
