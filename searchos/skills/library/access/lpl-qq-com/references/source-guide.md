# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# LPL (League of Legends Pro League) Data Access Skill

This skill retrieves data from the official LPL website (lpl.qq.com), providing access to:
- Season and tournament information
- Team listings and details
- Rank/statistics data (when available)

## Features

### 1. Get Seasons (`get_seasons`)
Retrieves all available seasons and tournaments from 2016 to present.

**Example:**
```json
{
  "function": "get_seasons"
}
```

**Returns:**
- List of seasons with domestic and international tournaments
- Each tournament includes name, game ID, stage IDs, and URL

### 2. Get Teams (`get_teams`)
Retrieves the complete list of all teams in the database.

**Example:**
```json
{
  "function": "get_teams"
}
```

**Returns:**
- Complete team list with IDs, names, logos, and other details
- Over 1000+ teams from various regions and tournaments

### 3. Get Team Detail (`get_team_detail`)
Retrieves detailed information for a specific team.

**Parameters:**
- `team_id`: The team's ID (required)

**Example:**
```json
{
  "function": "get_team_detail",
  "team_id": "1"
}
```

**Returns:**
- Team name, logo, statistics
- Player roster information

### 4. Get Rank Data (`get_rank_data`)
Attempts to retrieve rank statistics for a specific season.

**Parameters:**
- `season_id`: Season ID (default: "237" for 2026 season)
- `data_type`: Type of data - "team", "player", or "hero" (default: "player")
- `stage_ids`: Comma-separated stage IDs (optional)

**Example:**
```json
{
  "function": "get_rank_data",
  "season_id": "237",
  "data_type": "player"
}
```

**Note:** The rank API endpoints may not be directly accessible due to server-side restrictions. If this fails, use `get_rank_page_content` instead.

### 5. Get Rank Page Content (`get_rank_page_content`)
Renders the rank page and extracts visible content.

**Parameters:**
- `season_id`: Season ID (default: "237")
- `stage_ids`: Comma-separated stage IDs (optional)

**Example:**
```json
{
  "function": "get_rank_page_content",
  "season_id": "237"
}
```

**Returns:**
- Page configuration and available tabs
- Table headers for team/player/hero statistics
- Any visible data rows (may be empty if API is blocked)

## Data Sources

The skill uses the following data sources:
1. **EventdataTab.js** - Season and tournament information
2. **LOL_MATCH2_TEAM_LIST.js** - Complete team database
3. **Rank page** - Statistics and rankings (browser-rendered)

## Season IDs Reference

Common season IDs:
- 237: 2026 LPL Season
- 239: 2026 Mid-Season Invitational
- 238: 2026 First Stand
- 229: 2025 World Championship
- 218: 2025 LPL Season

## Notes

- The rank data API endpoints (`/compound/public/team`, `/compound/public/player`, `/compound/public/hero`) may return 404 errors due to server-side restrictions
- For reliable data, use `get_seasons` and `get_teams` functions
- The website uses GBK encoding for some resources, which is handled automatically
- All data is in Chinese as the source is the Chinese LPL official website
