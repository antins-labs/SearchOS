# Women's Volleybox Data Access Skill

This skill extracts structured data from women.volleybox.net, a comprehensive database for women's volleyball tournaments, teams, and players.

## Overview

Women.volleybox.net is a sports database that maintains detailed records of:
- Tournament classifications and final standings
- Team participation in various competitions
- Match results and schedules
- Player rosters and statistics

The site is protected by Cloudflare, so this skill uses Playwright-based browser automation to extract data from server-side rendered HTML.

## Functions

### get_tournament_classification

Extracts the final classification/rankings from a tournament page.

**Parameters:**
- `tournament_url` (required): Tournament identifier or full URL
  - Examples: 
    - `"women-the-olympics-2024-o30223"`
    - `"women-montreux-volley-masters-2005-o3753"`
    - Full URL: `"https://women.volleybox.net/women-the-olympics-2024-o30223"`

**Returns:**
```json
{
  "success": true,
  "tournament_name": "The Olympics 2024",
  "tournament_id": "30223",
  "tournament_url": "https://women.volleybox.net/women-the-olympics-2024-o30223",
  "classification": [
    {
      "rank": 1,
      "team_name": "Italy",
      "country_code": "IT",
      "team_id": "922",
      "team_url": "https://women.volleybox.net/italy-t922"
    },
    ...
  ],
  "total_teams": 12
}
```

**URL Patterns:**
- Tournament URLs follow the pattern: `{tournament-name}-o{id}`
- Examples:
  - Olympics: `women-the-olympics-{year}-o{id}`
  - World Championships: `women-world-championships-{year}-o{id}`
  - Nations League: `women-volleyball-nations-league-{year}-o{id}`

### get_team_tournaments

Extracts all tournaments a team has participated in.

**Parameters:**
- `team_url` (required): Team identifier or full URL
  - Examples:
    - `"usa-t1255"`
    - `"brazil-t724"`
    - Full URL: `"https://women.volleybox.net/usa-t1255"`
- `limit` (optional): Maximum number of tournaments to return (default: 50)

**Returns:**
```json
{
  "success": true,
  "team_name": "USA",
  "team_id": "1255",
  "team_url": "https://women.volleybox.net/usa-t1255",
  "tournaments": [
    {
      "name": "Nations League 2027",
      "tournament_id": "44082",
      "url": "https://women.volleybox.net/women-volleyball-nations-league-2027-o44082"
    },
    {
      "name": "The Olympics 2024",
      "tournament_id": "30223",
      "url": "https://women.volleybox.net/women-the-olympics-2024-o30223"
    },
    ...
  ],
  "total_tournaments": 50
}
```

**Team URL Patterns:**
- Team URLs follow the pattern: `{country-name}-t{id}`
- Examples:
  - `"usa-t1255"`
  - `"brazil-t724"`
  - `"china-t760"`
  - `"italy-t922"`

### get_team_info

Extracts basic information about a team.

**Parameters:**
- `team_url` (required): Team identifier or full URL (same as above)

**Returns:**
```json
{
  "success": true,
  "team_name": "USA",
  "team_id": "1255",
  "team_url": "https://women.volleybox.net/usa-t1255",
  "tournaments_count": 229,
  "matches_count": 842,
  "followers_count": 159,
  "ranking": 2
}
```

## Usage Examples

### Example 1: Get tournament classification

```json
{
  "function": "get_tournament_classification",
  "tournament_url": "women-the-olympics-2024-o30223"
}
```

### Example 2: Get recent tournaments for a team

```json
{
  "function": "get_team_tournaments",
  "team_url": "brazil-t724",
  "limit": 20
}
```

### Example 3: Get team information

```json
{
  "function": "get_team_info",
  "team_url": "italy-t922"
}
```

## Data Available

### Tournaments
- Olympics (2024, 2021, 2016, etc.)
- World Championships
- Nations League
- Continental Championships
- World Cup
- Grand Prix
- And many more...

### Teams
- All major women's national teams
- With complete tournament histories
- Rankings and statistics

## Notes

1. **Rate Limiting**: The skill uses browser automation which is slower than direct HTTP requests. Allow a few seconds per request.

2. **URL Flexibility**: You can use either:
   - Short identifiers (e.g., `"usa-t1255"`)
   - Full URLs (e.g., `"https://women.volleybox.net/usa-t1255"`)
   - URLs with suffixes (the skill automatically removes `/classification`, `/table`, etc.)

3. **Historical Data**: The database includes tournaments going back to the 1950s and earlier.

4. **Cloudflare Protection**: The site uses Cloudflare protection, so direct HTTP requests will fail. This skill uses Playwright for reliable data extraction.

## Common Tournament IDs

Some frequently requested tournaments:
- Olympics 2024: `o30223`
- Olympics 2021: `o8363`
- World Championship 2022: `o26544`
- Nations League 2024: `o30705`

Find tournament IDs by:
1. Browsing the site manually
2. Searching for team tournaments
3. Looking at URL patterns (they include the year)