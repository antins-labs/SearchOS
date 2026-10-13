# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Strafe.com News Access Skill

Fetch esports news articles from [Strafe.com](https://www.strafe.com/news/), including structured extraction of player awards, all-star teams, and tournament rosters.

## Features

### 1. Get News List (`get_news_list`)
Retrieve the latest esports news articles from Strafe.

**Parameters:** None required

**Returns:**
- List of recent articles with:
  - `title` - Article headline
  - `url` - Full article URL
  - `excerpt` - Brief preview text
  - `imageUrl` - Thumbnail image (if available)
  - `category` - Game/esport category (if available)
  - `date` - Publication date (if available)

**Example:**
```json
{
  "function": "get_news_list"
}
```

### 2. Get Article (`get_article`)
Fetch a single news article with full content.

**Parameters:**
- `url` (required) - Article URL or slug

**Returns:**
- `title` - Article headline
- `description` - Meta description
- `author` - Author name (if available)
- `date` - Publication date
- `content` - List of paragraph strings
- `players` - List of mentioned players with URLs
- `teams` - List of mentioned teams with URLs

**Example:**
```json
{
  "function": "get_article",
  "url": "lcs-summer-2026-schedule-format-rosters-tickets"
}
```

### 3. Get Awards Article (`get_awards_article`)
Specialized extraction for award announcements, all-star teams, and roster reveals. Automatically parses structured data like MVP awards, all-pro teams, and coaching staff.

**Parameters:**
- `url` (required) - Article URL or slug

**Returns:**
- `title` - Article headline
- `description` - Meta description
- `awards` - Dict mapping award names to lists of recipients:
  ```json
  {
    "Split MVP": ["Yu \"JackeyLove\" Wen-Bo (TES)"],
    "All-LPL First Team": [
      "Top: Kang \"TheShy\" Seung-lok (IG)",
      "Jungle: Seo \"Kanavi\" Jin-hyeok (TES)",
      ...
    ]
  }
  ```
- `players` - List of players with:
  - `name` - Player name/alias
  - `url` - Link to player page
  - `team` - Team code (e.g., "TES", "IG") if detected
  - `role` - Position/role (e.g., "Top", "ADC") if detected
- `teams` - List of mentioned teams with URLs

**Example:**
```json
{
  "function": "get_awards_article",
  "url": "jackeylove-takes-the-crown-all-2025-lpl-split-3-awards"
}
```

## Use Cases

- **Esports news aggregation**: Pull latest news from multiple games
- **Award tracking**: Extract structured award winners and all-star teams
- **Roster monitoring**: Track player mentions and team references
- **Content analysis**: Parse player/team data from news articles

## Notes

- Pages may load slowly; the skill handles timeouts gracefully
- Award extraction works best on articles with h3 headers followed by lists
- Player detection relies on Strafe's internal player page links (`/player/` URLs)
- Team detection relies on Strafe's team page links (`/team/` URLs)
