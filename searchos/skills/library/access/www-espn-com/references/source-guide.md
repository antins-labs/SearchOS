# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# ESPN Player Stats Access Skill

This skill fetches athlete profiles and statistics from ESPN's API for various sports leagues including NBA, NFL, MLB, NHL, and college sports.

## Features

- **Search Athletes**: Find athletes by name across all supported sports
- **Get Athlete Info**: Retrieve detailed biographical information
- **Get Athlete Stats**: Access comprehensive career statistics
- **Get Complete Profile**: Fetch both info and stats in one call
- **Get Stats Tables**: Get statistics formatted as tables for easy reading

## Supported Sports

| Code | Sport | League |
|------|-------|--------|
| `nba` | Basketball | NBA |
| `nfl` | Football | NFL |
| `mlb` | Baseball | MLB |
| `nhl` | Hockey | NHL |
| `ncaam` | Basketball | NCAA Men's |
| `ncaaf` | Football | NCAA Football |

## Usage Examples

### Search for Athletes

```json
{
  "function": "search",
  "query": "lebron james",
  "limit": 5
}
```

Returns a list of matching athletes with their IDs, teams, and headshots.

### Get Athlete Info

```json
{
  "function": "get_info",
  "athlete_id": "1966",
  "sport": "nba"
}
```

Returns biographical info including name, team, position, height, weight, jersey number, etc.

### Get Athlete Stats

```json
{
  "function": "get_stats",
  "athlete_id": "1966",
  "sport": "nba",
  "season_type": "2"
}
```

Returns detailed statistics organized by category (averages, totals, misc) with season-by-season breakdowns.

### Get Complete Profile

```json
{
  "function": "get_profile",
  "athlete_id": "3975",
  "sport": "nba"
}
```

Returns both athlete info and statistics in a single response.

### Get Stats as Tables

```json
{
  "function": "get_stats_tables",
  "athlete_id": "3139477",
  "sport": "nfl",
  "category": "averages"
}
```

Returns statistics formatted as tables with headers and rows.

## Known Athlete IDs

Some well-known athlete IDs for testing:

| Athlete | Sport | ID |
|---------|-------|-----|
| LeBron James | NBA | 1966 |
| Stephen Curry | NBA | 3975 |
| Patrick Mahomes | NFL | 3139477 |
| Tom Brady | NFL | 2330 |

## Response Structure

### Search Response
```json
{
  "query": "lebron",
  "count": 1,
  "athletes": [
    {
      "id": "1966",
      "name": "LeBron James",
      "sport": "basketball",
      "league": "nba",
      "team": "Los Angeles Lakers",
      "headshot": "https://...",
      "link": "https://..."
    }
  ]
}
```

### Stats Response
```json
{
  "athlete_id": "1966",
  "sport": "nba",
  "categories": [
    {
      "name": "averages",
      "display_name": "Regular Season Averages",
      "labels": ["GP", "GS", "MIN", "FG", "FG%", ...],
      "totals": ["1622", "1620", "37.6", ...],
      "seasons": [
        {
          "season": "2023-24",
          "team_slug": "los-angeles-lakers",
          "stats": ["71", "71", "35.3", ...],
          "stats_dict": {"GP": "71", "GS": "71", ...}
        }
      ]
    }
  ]
}
```

## Notes

- Season type `2` = Regular Season, `3` = Postseason
- Stats are organized by category (averages, totals, miscellaneous for NBA; passing, rushing, receiving, etc. for NFL)
- Each category includes career totals and season-by-season breakdowns
- Team slugs are URL-friendly identifiers (e.g., "los-angeles-lakers")
