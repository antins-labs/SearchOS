# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# FBref.com Access Skill

This skill retrieves football/soccer statistics from [FBref.com](https://fbref.com), one of the most comprehensive football statistics databases on the web. FBref provides detailed statistics for teams, players, and competitions worldwide.

## Features

- **Squad Statistics**: Retrieve complete team statistics including standard stats, goalkeeper stats, shooting, passing, defensive actions, possession, and more
- **Competition Statistics**: Get league/competition tables and statistics
- **Player Statistics**: Access individual player performance data
- **Team Search**: Search for teams by name

## Available Functions

### get_squad_stats

Retrieves comprehensive statistics for a team squad.

**Parameters:**
- `url` (required): The FBref squad page URL

**Example URL formats:**
- `https://fbref.com/en/squads/e2d8892c/Paris-Saint-Germain-Stats` - Current season
- `https://fbref.com/en/squads/e2d8892c/2024-2025/Paris-Saint-Germain-Stats` - Specific season
- `https://fbref.com/en/squads/e2d8892c/2024-2025/c8/Paris-Saint-Germain-Stats-Champions-League` - Specific competition

**Returns:**
- Team information (name, season, competition)
- All statistical tables found on the page
- Table data includes headers, rows, and data-stat attributes

### get_competition_stats

Retrieves statistics for a competition/league.

**Parameters:**
- `url` (required): The FBref competition page URL

**Example URL formats:**
- `https://fbref.com/en/comps/8/Champions-League-Stats`
- `https://fbref.com/en/comps/9/Premier-League-Stats`
- `https://fbref.com/en/comps/12/La-Liga-Stats`

### get_player_stats

Retrieves statistics for an individual player.

**Parameters:**
- `url` (required): The FBref player page URL

**Example URL format:**
- `https://fbref.com/en/players/.../Player-Name`

### search_teams

Search for teams by name.

**Parameters:**
- `query` (required): Team name search query

**Returns:**
- List of matching teams with names and URLs

## Important Notes

### Cloudflare Protection

FBref.com uses Cloudflare protection which may block automated access. This skill implements multiple anti-detection measures:
- Realistic browser fingerprint
- Stealth scripts to avoid bot detection
- Automatic challenge waiting

However, access may still be restricted in some environments. If you encounter persistent "Cloudflare challenge not passed" errors:
1. Try again later - Cloudflare's restrictions may be temporary
2. Use a different network/IP address
3. Consider that some data centers or VPNs may be permanently blocked

### Rate Limiting

FBref is a free resource provided by Sports Reference. Please be respectful:
- Don't make excessive requests in a short time
- Cache results when possible
- Consider supporting FBref through their donation options

### Data Tables

FBref pages contain multiple statistical tables. The skill attempts to extract all tables found on the page. Common table IDs include:
- `stats_standard` - Standard statistics
- `stats_keeper` - Goalkeeper statistics
- `stats_shooting` - Shooting statistics
- `stats_passing` - Passing statistics
- `stats_defense` - Defensive statistics
- `stats_possession` - Possession statistics
- `stats_playing_time` - Playing time statistics

## Example Usage

```python
# Get PSG Champions League stats
result = await execute({
    'function': 'get_squad_stats',
    'url': 'https://fbref.com/en/squads/e2d8892c/2024-2025/c8/Paris-Saint-Germain-Stats-Champions-League'
}, ctx)

# Search for a team
result = await execute({
    'function': 'search_teams',
    'query': 'Barcelona'
}, ctx)

# Get Premier League stats
result = await execute({
    'function': 'get_competition_stats',
    'url': 'https://fbref.com/en/comps/9/Premier-League-Stats'
}, ctx)
```

## Error Handling

The skill returns structured error responses:
- `cloudflare_challenge`: Cloudflare protection blocked access
- `http_error`: HTTP error (404, 500, etc.)
- `page_error`: Error parsing page content
- `missing_param`: Required parameter not provided
- `unknown_function`: Invalid function name

Each error response includes:
- `error`: Human-readable error message
- `error_type`: Error category for programmatic handling
- Additional context (URL, query, etc.)
