# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Sports Illustrated (SI.com) Access Skill

Retrieve articles from Sports Illustrated's website, including NBA, MLB, NFL, and other sports coverage.

## Features

- **Section Articles**: Get the latest articles from any sports section (NBA, MLB, NFL, etc.)
- **Article Content**: Fetch full article text with metadata (headline, author, date, body)
- **Search**: Find articles by keyword within a section

## Usage

### Get Section Articles

Retrieve the latest articles from a sports section:

```json
{
  "function": "get_section_articles",
  "section": "nba",
  "limit": 20
}
```

Available sections: `nba`, `mlb`, `nfl`, `nhl`, `college`, `soccer`, `fighting`, `golf`, `tennis`, `swim`, `racing`, `horse-racing`, `olympics`, `more`

### Get Single Article

Fetch full content of an article:

```json
{
  "function": "get_article",
  "url": "https://www.si.com/nba/free-agency/where-shaq-believes-lebron-james-should-sign-lakers-departure"
}
```

### Search Articles

Search for articles by keyword in a section:

```json
{
  "function": "search_articles",
  "query": "LeBron James",
  "section": "nba",
  "limit": 10
}
```

## Response Format

### Section Articles Response

```json
{
  "success": true,
  "section": "nba",
  "url": "https://www.si.com/nba/",
  "count": 20,
  "articles": [
    {
      "headline": "Article Title",
      "description": "Article description/summary",
      "author": "Author Name",
      "datePublished": "2024-01-15T10:30:00Z",
      "dateModified": "2024-01-15T11:00:00Z",
      "url": "https://www.si.com/nba/...",
      "image": "https://images2.minutemediacdn.com/..."
    }
  ]
}
```

### Article Response

```json
{
  "success": true,
  "article": {
    "url": "https://www.si.com/nba/...",
    "headline": "Article Title",
    "author": "Author Name",
    "datePublished": "2024-01-15T10:30:00Z",
    "dateModified": "2024-01-15T11:00:00Z",
    "description": "Article description",
    "image": "https://...",
    "body": "Full article text with paragraphs separated by double newlines...",
    "tags": ["LeBron James", "Los Angeles Lakers", "NBA"],
    "section": "NBA"
  }
}
```

## Notes

- The skill uses browser automation (Playwright) to handle JavaScript rendering
- Article metadata is extracted from JSON-LD structured data
- Article body text is extracted from the DOM
- Section pages typically return 30-50 articles
- Some older article URLs may return 404 errors as SI.com's URL structure changes

## Technical Details

- **Rendering**: JavaScript-heavy site requiring browser automation
- **Data Sources**: JSON-LD structured data, DOM extraction, window.clientApiData
- **Timeout**: 60 second default for page loads
- **User Agent**: Standard Chrome user agent to avoid blocking
