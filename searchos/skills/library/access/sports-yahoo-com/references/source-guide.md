# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Yahoo Sports Access Skill

Extracts content from Yahoo Sports (sports.yahoo.com) including articles, NBA news, and player information.

## Features

- **Article Extraction**: Extracts headline, description, author, publish date, keywords, and images from Yahoo Sports articles
- **NBA News**: Gets the latest NBA news headlines from the NBA section
- **NBA Players**: Retrieves NBA player listings

## Functions

### get_article

Extracts article content from a Yahoo Sports URL.

**Parameters:**
- `url` (required): The Yahoo Sports article URL

**Example:**
```json
{
  "function": "get_article",
  "url": "https://sports.yahoo.com/report-kings-waiving-rookie-guard-182840265.html"
}
```

**Returns:**
```json
{
  "success": true,
  "article": {
    "url": "https://sports.yahoo.com/report-kings-waiving-rookie-guard-182840265.html",
    "title": "Kings waive Ellis, sign Shaq's son Shareef in flurry of roster moves - Yahoo Sports",
    "headline": "Kings waive Ellis, sign Shaq's son Shareef in flurry of roster moves",
    "description": "Undrafted guard Boogie Ellis impressed during the preseason...",
    "image": "https://s.yimg.com/os/en/...",
    "keywords": "The Kings, Boogie Ellis, NBA season opener...",
    "keywords_list": ["The Kings", "Boogie Ellis", ...],
    "site_name": "Yahoo Sports"
  }
}
```

### get_nba_news

Gets NBA news headlines from the NBA section.

**Parameters:** None

**Example:**
```json
{
  "function": "get_nba_news"
}
```

**Returns:**
```json
{
  "success": true,
  "page": {
    "url": "https://sports.yahoo.com/nba/",
    "title": "NBA News, Scores, Standings, Schedules, Videos and more - Yahoo Sports",
    "description": "Sports News, Scores, Fantasy Games",
    "articles": [
      {
        "url": "https://sports.yahoo.com/...",
        "title": "Article headline..."
      }
    ]
  }
}
```

### get_nba_players

Gets NBA player listings.

**Parameters:** None

**Example:**
```json
{
  "function": "get_nba_players"
}
```

**Returns:**
```json
{
  "success": true,
  "page": {
    "url": "https://sports.yahoo.com/nba/players/",
    "title": "NBA Players - Yahoo Sports",
    "players": [
      {
        "url": "https://sports.yahoo.com/nba/players/...",
        "name": "Player Name"
      }
    ]
  }
}
```

## Technical Notes

- Uses Playwright browser automation to handle Yahoo's anti-bot measures
- Extracts content from Open Graph, Twitter Card, and JSON-LD metadata
- Handles page timeouts gracefully by extracting available content
- No external API dependencies required

## Limitations

- Full article body text may not be available for all articles due to anti-bot restrictions
- Player listings may be limited to what's visible in the initial page load
- Some content may require JavaScript rendering which could timeout in restricted environments
