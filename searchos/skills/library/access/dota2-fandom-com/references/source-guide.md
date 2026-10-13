# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Dota 2 Fandom Wiki Access Skill

Fetches tournament data, hero information, player profiles, and other content from dota2.fandom.com.

## Why This Skill Exists

The Dota 2 Fandom wiki uses Cloudflare protection that blocks direct HTTP requests and returns only a tracking pixel/challenge page. This skill uses the MediaWiki API endpoint which bypasses the Cloudflare protection and provides structured access to all wiki content.

## Functions

### search
Search for wiki pages matching a query.

**Parameters:**
- `query` (required): Search keywords
- `limit` (optional): Number of results (default: 20, max: 50)

**Example:**
```json
{
  "function": "search",
  "query": "The International",
  "limit": 10
}
```

**Returns:**
- List of matching pages with title, pageid, snippet, and URL

### get_tournament
Get detailed tournament page data including infobox, prize distribution, and standings.

**Parameters:**
- `page` (required): Tournament page name (e.g., "The_International_2014")

**Example:**
```json
{
  "function": "get_tournament",
  "page": "The_International_2014"
}
```

**Returns:**
- `infobox`: Tournament details (dates, prize pool, teams, location, version)
- `prize_distribution`: List of team placements with winnings
- `standings`: Group stage standings if available
- `sections`: Page section headings
- `text_preview`: First 3000 characters of readable content

### get_hero
Get hero page data with stats and abilities.

**Parameters:**
- `page` (required): Hero name (e.g., "Invoker", "Pudge", "Anti-Mage")

**Example:**
```json
{
  "function": "get_hero",
  "page": "Invoker"
}
```

**Returns:**
- `infobox`: Hero stats and attributes
- `sections`: Page section headings (abilities, lore, etc.)
- `text_preview`: First 3000 characters of readable content

### get_player
Get player profile data.

**Parameters:**
- `page` (required): Player name/ID (e.g., "N0tail", "Puppey", "Arteezy")

**Example:**
```json
{
  "function": "get_player",
  "page": "N0tail"
}
```

**Returns:**
- `infobox`: Player details (name, team, role, country, signature heroes)
- `sections`: Page section headings
- `text_preview`: First 3000 characters of readable content

### get_page
Get any wiki page content (generic fallback).

**Parameters:**
- `page` (required): Page name

**Returns:**
- `infobox`: Infobox data if present
- `sections`: Page section headings
- `text_preview`: First 5000 characters of readable content

## Page Name Format

Page names should use underscores for spaces (wiki URL format):
- ✅ "The_International_2014"
- ✅ "The International 2014" (also works)
- ✅ "Team_Liquid"
- ✅ "Evil Geniuses"

## Common Tournament Pages

- "The_International_2014" through "The_International_2022" (TI series)
- "The_International" (main TI overview page)
- Major tournament pages vary by name

## Notes

- All data is fetched from the MediaWiki API, which provides reliable access without Cloudflare challenges
- Prize distribution parsing looks for tables containing "$" and "USD" markers
- Infobox extraction handles the standard Fandom wiki infobox table format
- The skill returns structured data rather than raw HTML for easier consumption
