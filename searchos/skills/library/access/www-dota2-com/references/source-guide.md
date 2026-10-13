# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Dota2.com Access Skill

This skill extracts structured content from the official Dota 2 website (www.dota2.com).

## Supported Content Types

### 1. News Entries (`get_news_entry`)

Extract news article content including:
- Title
- Publication date
- Article content/body
- Featured image URL
- Full text content

**Example URL:** `https://www.dota2.com/newsentry/3398555399437783294`

**Example Usage:**
```json
{
  "function": "get_news_entry",
  "url": "https://www.dota2.com/newsentry/3398555399437783294"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "news_id": "3398555399437783294",
    "title": "The International Grand Champions",
    "date": "November 1, 2022",
    "description": "The Road to the Aegis...",
    "content": "Full article content...",
    "image_url": "https://...",
    "url": "https://www.dota2.com/newsentry/3398555399437783294"
  }
}
```

### 2. Tournament Brackets (`get_tournament_bracket`)

Extract tournament bracket data from The International 2012 pages, including:
- Grand Finals match results with game-by-game breakdown
- Winners bracket team listings
- Losers bracket with elimination information

**Supported URLs:**
- Grand Finals: `http://www.dota2.com/tournaments/international2012/mainevent/results/grandfinal/`
- Winners Bracket: `http://www.dota2.com/tournaments/international2012/mainevent/results/winners/`
- Losers Bracket: `http://www.dota2.com/tournaments/international2012/mainevent/results/losers/`

**Example Usage:**
```json
{
  "function": "get_tournament_bracket",
  "url": "http://www.dota2.com/tournaments/international2012/mainevent/results/grandfinal/"
}
```

**Returns (Grand Finals):**
```json
{
  "success": true,
  "data": {
    "tournament_name": "The International 2012",
    "bracket_type": "grand_final",
    "matches": [
      {
        "game": 1,
        "team1": "Na'Vi",
        "team1_result": "L",
        "team2": "iG",
        "team2_result": "W",
        "winner": "iG",
        "game_url": "http://www.dota2.com/tournaments/international2012/game/40/"
      },
      ...
    ],
    "team_logos": {
      "navi_logo_list": "http://media.steampowered.com/apps/dota2/images/international2012/teams/navi_logo_list.png",
      "ig_logo_list": "http://media.steampowered.com/apps/dota2/images/international2012/teams/ig_logo_list.png"
    }
  }
}
```

### 3. Tournament Game Details (`get_tournament_game`)

Extract details from individual tournament game pages.

**Example URL:** `http://www.dota2.com/tournaments/international2012/game/40/`

**Example Usage:**
```json
{
  "function": "get_tournament_game",
  "url": "http://www.dota2.com/tournaments/international2012/game/40/"
}
```

## Technical Details

- Uses Playwright browser automation to handle JavaScript-rendered content
- The news pages use React-based rendering which requires browser execution
- Tournament pages are static HTML with structured match data
- Extracts data from both DOM elements and embedded metadata (OpenGraph tags)

## Error Handling

All functions return a consistent error format:
```json
{
  "success": false,
  "error": "Error description",
  "error_type": "ExceptionType"
}
```
