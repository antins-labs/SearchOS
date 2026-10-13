# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# NBA.com Access Skill

This skill retrieves news articles, games schedule/scores, and player/team statistics from NBA.com.

## Functions

### fetch_article

Fetches a specific NBA news article by URL.

**Parameters:**
- `url` (required): Full URL to the NBA.com article (must start with `https://www.nba.com/news/`)

**Returns:**
- Article title, slug, URL
- Full content text and word count
- Excerpt/summary
- Author name
- Publication date and last modified date
- Category and taxonomy (teams, players, categories mentioned)
- Cover image URL
- Related articles (up to 5)

**Example:**
```json
{
  "function": "fetch_article",
  "url": "https://www.nba.com/news/horry-scale-nikola-jokic-game-winner-39-foot-buzzer-beater"
}
```

### fetch_games

Fetches NBA games schedule and scores from the games page.

**Parameters:**
- `date` (optional): Specific date in YYYY-MM-DD format (defaults to current date)

**Returns:**
- Selected date
- Featured/highlighted events
- Total event count
- Games count by date for the current year

**Example:**
```json
{
  "function": "fetch_games"
}
```

### fetch_stats

Fetches NBA statistics and leaders from the stats homepage.

**Parameters:**
None required.

**Returns:**
- Daily leaders (points, rebounds, assists, etc.)
- Nightly leaders (top performers from recent games)
- Season leaders (season-long statistical leaders)
- Team nightly leaders
- Team season leaders
- Each category includes top 5 players/teams with their stats

**Example:**
```json
{
  "function": "fetch_stats"
}
```

## Data Source

All data is extracted from the `__NEXT_DATA__` JSON payload embedded in NBA.com's Next.js pages. This provides structured, reliable access to:

- News articles with full content, metadata, and related content
- Games schedule with event information
- Statistical leaders across multiple categories (points, rebounds, assists, etc.)

## Notes

- The skill uses direct HTTP requests to fetch pages; no browser automation is required
- Data is extracted from server-side rendered Next.js payloads
- Rate limiting may apply; use responsibly
- All timestamps are in UTC format
