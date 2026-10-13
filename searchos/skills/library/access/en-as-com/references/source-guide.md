# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# AS English (en.as.com) Sports News Access Skill

This skill provides access to AS English sports news content from en.as.com, with specialized extraction for player roster lists commonly found in sports articles.

## Features

### 1. Article Extraction (`get_article`)

Extracts full article content including:
- **Metadata**: Title, author, publication date, description, featured image
- **Body content**: Paragraphs, section headers, and embedded lists
- **Roster lists**: Specialized extraction for player rosters (NBA All-Star teams, lineups, etc.)

The roster extraction feature is designed to handle AS.com's article structure where player lists are organized under section headers like "Western Conference Starters" or "Eastern Conference Reserves".

**Example usage:**
```json
{
  "function": "get_article",
  "url": "https://en.as.com/nba/2024-nba-all-star-game-rosters-full-list-of-players-for-both-teams-n/"
}
```

**Returns:**
```json
{
  "success": true,
  "article": {
    "url": "...",
    "title": "2024 NBA All-Star Game rosters: full list of players for both teams",
    "author": "Paul Rudder",
    "published_time": "2024-02-14T05:49:13-05:00",
    "description": "...",
    "image": "..."
  },
  "rosters": {
    "Western Conference Starters": [
      "LeBron James (Los Angeles Lakers)",
      "Nikola Jokic (Denver Nuggets)",
      ...
    ],
    "Western Conference Reserves": [...],
    "Eastern Conference Starters": [...],
    "Eastern Conference Reserves": [...]
  },
  "content": {
    "headers": [...],
    "paragraphs": [...],
    "lists": {...}
  }
}
```

### 2. Article Listing (`list_articles`)

Lists the latest NBA articles from the AS English NBA section.

**Example usage:**
```json
{
  "function": "list_articles",
  "limit": 10
}
```

**Returns:**
```json
{
  "success": true,
  "section": "NBA",
  "section_url": "https://en.as.com/nba/",
  "count": 10,
  "articles": [
    {
      "url": "https://en.as.com/nba/...",
      "position": 1,
      "title": "Article title",
      "image_url": "..."
    },
    ...
  ]
}
```

## Parameters

| Parameter | Function | Required | Description |
|-----------|----------|----------|-------------|
| `function` | All | Yes | Either `get_article` or `list_articles` |
| `url` | get_article | Yes | Full URL to the AS English article |
| `include_rosters` | get_article | No | Extract roster lists (default: true) |
| `include_body` | get_article | No | Extract full body content (default: true) |
| `limit` | list_articles | No | Max articles to return (default: 20, max: 50) |

## Use Cases

1. **Extract NBA All-Star rosters**: The specialized roster extraction captures player lists organized by conference and starter/reserve status.

2. **Get latest NBA news**: Use `list_articles` to discover recent NBA articles.

3. **Read full article content**: Extract complete article text with structured headers and paragraphs.

## Notes

- The roster extraction works best with articles that have clearly structured player lists under section headers.
- AS.com uses `div.a_de_txt` containers for roster lists, which this skill specifically targets.
- Article URLs should be from the `en.as.com` domain.
- The skill handles both standard articles and list-based content.
