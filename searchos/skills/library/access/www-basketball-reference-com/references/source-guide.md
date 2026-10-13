# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Basketball Reference Access Skill

This skill fetches basketball statistics data from [Basketball Reference](https://www.basketball-reference.com), the most comprehensive basketball statistics database on the web.

## Features

- **Team Rosters**: Get complete team rosters with player info (number, position, height, weight, experience, college)
- **Team Statistics**: Comprehensive team stats including per-game, totals, advanced metrics, shooting splits, and more
- **Player Statistics**: Full career statistics for any player including regular season and playoffs
- **Game Box Scores**: Detailed game statistics with player breakdowns, line scores, and four factors
- **Table Extraction**: Generic table extraction from any Basketball Reference page

## Usage Examples

### Get Team Roster

```python
# By URL
execute({
    "function": "get_team_roster",
    "url": "https://www.basketball-reference.com/teams/SAC/2025.html"
})

# By team abbreviation and season
execute({
    "function": "get_team_roster",
    "team_abbr": "SAC",
    "season": "2025"
})
```

Returns team info and roster table with all players.

### Get Team Stats

```python
execute({
    "function": "get_team_stats",
    "team_abbr": "LAL",
    "season": "2024"
})
```

Returns multiple stat tables:
- `per_game_stats` - Per game statistics
- `totals_stats` - Season totals
- `advanced` - Advanced metrics (PER, TS%, etc.)
- `shooting` - Shooting breakdowns by distance
- And more...

### Get Player Stats

```python
# By URL
execute({
    "function": "get_player_stats",
    "url": "https://www.basketball-reference.com/players/j/jamesle01.html"
})

# By player ID
execute({
    "function": "get_player_stats",
    "player_id": "curryst01"
})
```

Returns player career statistics with regular season and playoff data.

### Get Box Score

```python
# By URL
execute({
    "function": "get_boxscore",
    "url": "https://www.basketball-reference.com/boxscores/202410240SAC.html"
})

# By date and home team
execute({
    "function": "get_boxscore",
    "game_date": "20241024",
    "home_team": "SAC"
})
```

Returns:
- Line score (final scores)
- Four factors
- Basic and advanced box scores for both teams

### List Tables on a Page

```python
execute({
    "function": "list_tables",
    "url": "https://www.basketball-reference.com/teams/BOS/2024.html"
})
```

Returns all table IDs on the page with row/column counts.

### Get Specific Table

```python
execute({
    "function": "get_table",
    "url": "https://www.basketball-reference.com/players/j/jamesle01.html",
    "table_id": "advanced"
})
```

## Common Table IDs

### Team Pages
- `roster` - Team roster
- `per_game_stats` - Per game statistics
- `totals_stats` - Season totals
- `per_minute_stats` - Per 36 minutes
- `per_poss` - Per 100 possessions
- `advanced` - Advanced statistics
- `shooting` - Shooting breakdowns
- `adj_shooting` - Adjusted shooting
- `pbp_stats` - Play-by-play stats
- `salaries2` - Player salaries

### Player Pages
- `per_game_stats` - Per game career stats
- `totals_stats` - Career totals
- `per_minute_stats` - Per 36 minutes
- `advanced` - Advanced metrics
- `per_game_stats_post` - Playoff per game
- `totals_stats_post` - Playoff totals

### Box Score Pages
- `line_score` - Final score by quarter
- `four_factors` - Four factors summary
- `box-{TEAM}-game-basic` - Basic box score for team
- `box-{TEAM}-game-advanced` - Advanced box score for team

## Notes

- The site blocks direct HTTP requests, so this skill uses browser automation (Playwright)
- Data includes hyperlinks for player/team names where applicable
- All numerical statistics are returned as text strings to preserve formatting
- Some pages may take longer to load due to dynamic content
