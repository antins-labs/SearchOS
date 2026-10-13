# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# GOL.gg - League of Legends Esports Statistics

Access League of Legends professional esports statistics from [gol.gg](https://gol.gg), a comprehensive database for competitive LoL data.

## Available Functions

### Tournament Statistics

#### `get_tournament_stats`
Retrieve comprehensive tournament statistics including top performers and key metrics.

**Parameters:**
- `tournament_name` (required): Tournament name, e.g., "LPL 2025 Split 3"

**Returns:**
- Tournament info (draft mode, game count, average duration, etc.)
- Top KDA players
- Most kills in a single game
- Top kill participation
- Top team GPM
- Top farmers (CSM)
- Best farm performances

**Example:**
```json
{
  "function": "get_tournament_stats",
  "tournament_name": "LPL 2025 Split 3"
}
```

#### `get_tournament_ranking`
Get team rankings for a specific tournament.

**Parameters:**
- `tournament_name` (required): Tournament name

**Returns:**
- List of teams with win rates, wins, losses, game duration, GDM

**Example:**
```json
{
  "function": "get_tournament_ranking",
  "tournament_name": "LPL 2025 Split 3"
}
```

### Player Data

#### `get_players_list`
Retrieve a list of players with their statistics.

**Parameters:**
- `season` (optional): Season code, e.g., "S16" (default)
- `split` (optional): Split name: "Summer" (default), "Spring", "Winter"
- `tournament` (optional): Tournament filter, "ALL" (default) or specific tournament

**Returns:**
- List of players with stats: games, win rate, KDA, CSM, GPM, KP%, DMG%, etc.

**Example:**
```json
{
  "function": "get_players_list",
  "season": "S16",
  "split": "Summer"
}
```

#### `get_player_stats`
Get detailed statistics for a specific player.

**Parameters:**
- `player_id` (required): Player ID (numeric), found in player URLs
- `tournament` (optional): Tournament filter, "ALL" (default) or specific tournament

**Returns:**
- Player name and general stats (record, win rate, KDA, CSM)
- Personal best performances
- Early game statistics
- Champion pool with per-champion stats

**Example:**
```json
{
  "function": "get_player_stats",
  "player_id": "1708",
  "tournament": "LPL 2025 Split 3"
}
```

### Champion Data

#### `get_champions_list`
Retrieve champion statistics for a season/split.

**Parameters:**
- `season` (optional): Season code, default "S16"
- `split` (optional): Split name, default "Summer"
- `tournament` (optional): Tournament filter, default "ALL"

**Returns:**
- Champion picks, bans, priority score
- Win rate, KDA, average build time
- Gold trends, CSM, DPM, GPM
- CSD@15, GD@15, XPD@15

**Example:**
```json
{
  "function": "get_champions_list",
  "season": "S16",
  "split": "Summer"
}
```

### Team Data

#### `get_teams_list`
Retrieve a list of teams with statistics.

**Parameters:**
- `season` (optional): Season code, default "S16"
- `split` (optional): Split name, default "Summer"
- `tournament` (optional): Tournament filter, default "ALL"

**Returns:**
- List of teams with win rates, game stats, and performance metrics

**Example:**
```json
{
  "function": "get_teams_list",
  "season": "S16"
}
```

#### `get_team_stats`
Get detailed statistics for a specific team.

**Parameters:**
- `team_id` (required): Team ID (numeric), found in team URLs
- `tournament` (optional): Tournament filter, default "ALL"

**Returns:**
- Team name and general statistics
- Performance metrics

**Example:**
```json
{
  "function": "get_team_stats",
  "team_id": "2519"
}
```

## Data Notes

- The site uses season codes (S6, S7, ..., S16) to identify competitive seasons
- Splits are typically: Pre-Season, Winter, Spring, Summer
- Tournament names must match exactly as they appear on the site
- Player and team IDs can be found in the URLs when browsing the site

## Supported Leagues

The database covers major leagues including:
- LCK (Korea)
- LPL (China)
- LEC (Europe)
- LCS (North America)
- CBLOL (Brazil)
- LCP (Pacific)
- TCL (Turkey)
- And many regional leagues

## Error Handling

All functions return an `error` field in the response dictionary when something goes wrong, rather than raising exceptions. Check for this field to handle errors gracefully.
