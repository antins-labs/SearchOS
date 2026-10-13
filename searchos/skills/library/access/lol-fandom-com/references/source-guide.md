# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# lol.fandom.com Access Skill

This skill retrieves League of Legends esports tournament data from the League of Legends Fandom wiki (lol.fandom.com).

## Overview

The League of Legends Fandom wiki contains comprehensive esports data including:
- Tournament standings and results
- Player statistics (KDA, CS, damage, etc.)
- Team rosters
- Match schedules
- Awards (MVP, Rookie of the Split, etc.)

## Functions

### get_player_statistics

Retrieve detailed player statistics for a tournament.

**Parameters:**
- `tournament` (required): Tournament page path, e.g., "LPL/2025_Season/Split_3"
- `role` (optional): Filter by position (Top, Jungle, Mid, Bot, Support)
- `limit` (optional): Limit number of players returned

**Returns:**
- Player names, teams, and comprehensive stats including:
  - Games played (G), Wins (W), Losses (L), Win Rate (WR)
  - Kills (K), Deaths (D), Assists (A), KDA
  - Creep Score (CS, CS/M)
  - Vision Score (VS, VS/M)
  - Gold (G_Per, G/M)
  - Damage (DMG, DMG/M)
  - Kill Participation (KPAR)
  - Kill Share (KS), Gold Share (GS)
  - Champion pool (CP)

**Example:**
```json
{
  "function": "get_player_statistics",
  "tournament": "LPL/2025_Season/Split_3",
  "limit": 10
}
```

### get_tournament_info

Get general tournament information including sections and overview.

**Parameters:**
- `tournament` (required): Tournament page path

**Returns:**
- Tournament title, page ID, sections, and infobox data

**Example:**
```json
{
  "function": "get_tournament_info",
  "tournament": "LPL/2025_Season/Split_3"
}
```

### get_standings

Get tournament standings by group.

**Parameters:**
- `tournament` (required): Tournament page path

**Returns:**
- Group standings with rank, team, series record, game record, and streak

**Example:**
```json
{
  "function": "get_standings",
  "tournament": "LPL/2025_Season/Split_3"
}
```

### get_team_rosters

Get team rosters for a tournament.

**Parameters:**
- `tournament` (required): Tournament page path

**Returns:**
- List of teams with their player rosters

**Example:**
```json
{
  "function": "get_team_rosters",
  "tournament": "LPL/2025_Season/Split_3"
}
```

### get_match_schedule

Get match schedule and results.

**Parameters:**
- `tournament` (required): Tournament page path
- `limit` (optional): Maximum number of matches to return

**Returns:**
- Match results with teams, scores, and week/round information

**Example:**
```json
{
  "function": "get_match_schedule",
  "tournament": "LPL/2025_Season/Split_3",
  "limit": 20
}
```

### get_awards

Get tournament awards and MVP standings.

**Parameters:**
- `tournament` (required): Tournament page path

**Returns:**
- Season awards (MVP, Rookie of the Split, etc.)
- MVP standings by player

**Example:**
```json
{
  "function": "get_awards",
  "tournament": "LPL/2025_Season/Split_3"
}
```

### search_pages

Search for tournament pages on the wiki.

**Parameters:**
- `prefix` (required): Page prefix to search, e.g., "LPL/2025"
- `limit` (optional): Maximum number of results

**Returns:**
- List of matching page titles and IDs

**Example:**
```json
{
  "function": "search_pages",
  "prefix": "LPL/2025",
  "limit": 20
}
```

## Tournament Paths

Common tournament path patterns:
- LPL (China): `LPL/2025_Season/Split_3`
- LCK (Korea): `LCK/2025_Season/Summer`
- LEC (Europe): `LEC/2025_Season/Summer`
- World Championship: `Worlds/2025`

Use `search_pages` to discover available tournaments.

## Notes

- This skill uses the Fandom MediaWiki API to bypass Cloudflare protection
- Player statistics include per-game averages where applicable
- Standings may be organized by groups depending on tournament format
- Some tournaments may have additional statistics pages (e.g., Champion Statistics)
