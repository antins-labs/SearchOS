# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# navi.gg Tournament Data Access Skill

This skill extracts tournament information and match data from [navi.gg](https://navi.gg), the official website of Natus Vincere (NAVI) esports organization.

## Overview

The skill uses Playwright browser automation to bypass Cloudflare protection and extract structured data from tournament pages. It supports:

- **Tournament Information**: Name, dates, prize pool, location, status, and description
- **Match Data**: Team names, scores, stages, tournament info, and team logos

## Functions

### get_tournament_info

Fetches overview information for a specific tournament.

**Parameters:**
- `tournament_slug` (required): The tournament slug from the URL

**Example:**
```json
{
  "function": "get_tournament_info",
  "tournament_slug": "blasttv-austin-major-2025"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "slug": "blasttv-austin-major-2025",
    "url": "https://navi.gg/en/tournaments/blasttv-austin-major-2025",
    "name": "BLAST.tv Austin Major 2025",
    "sport": "Counter-Strike 2",
    "description": "The biggest summer CS2 tournament...",
    "startDate": "2025-04-14T03:00:00+03:00",
    "endDate": "2025-06-23T02:59:00+03:00",
    "eventStatus": "EventScheduled",
    "prizePool": "$1,250,000",
    "eventType": "LAN",
    "location": "Austin, United States",
    "status": "live"
  }
}
```

### get_matches

Fetches the match list for a tournament with team names, scores, and stages.

**Parameters:**
- `tournament_slug` (required): The tournament slug from the URL
- `limit` (optional): Maximum number of matches to return (default: 50)

**Example:**
```json
{
  "function": "get_matches",
  "tournament_slug": "blasttv-austin-major-2025",
  "limit": 20
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "tournament": {
      "name": "BLAST.tv Austin Major 2025",
      "sport": "Counter-Strike 2",
      "startDate": "2025-04-14T03:00:00+03:00",
      "endDate": "2025-06-23T02:59:00+03:00"
    },
    "matches": [
      {
        "team1": "Falcons",
        "team2": "MIBR",
        "mapsWonTeam1": 1,
        "mapsWonTeam2": 1,
        "status": "live",
        "tournamentInfo": "BLAST Austin Major / Swiss",
        "stage": "Swiss",
        "team1Logo": "https://img.navi.gg/teams/...",
        "team2Logo": "https://img.navi.gg/teams/..."
      },
      {
        "team1": "Vitality",
        "team2": "The MongolZ",
        "score1": 2,
        "score2": 1,
        "status": "completed",
        "stage": "Bracket"
      }
    ],
    "totalMatches": 20
  }
}
```

## Tournament Slugs

Tournament slugs can be found in the navi.gg URLs:

- `blasttv-austin-major-2025` - BLAST.tv Austin Major 2025
- `pgl-major-copenhagen-2024` - PGL Major Copenhagen 2024
- `iem-katowice-2024` - IEM Katowice 2024

Visit `https://navi.gg/en/tournaments` to see all available tournaments.

## Match Status Values

- `live` - Match is currently being played
- `completed` - Match has finished (has scores)
- `upcoming` - Match is scheduled but not yet started

## Notes

- The skill uses Playwright browser automation to handle Cloudflare protection
- All data is extracted from the public navi.gg website
- Match data includes NAVI matches as well as other tournament matches
- Team logos are provided as full URLs to navi.gg image servers
