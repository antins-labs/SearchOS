# GoRatings.org Access Skill

Access Go (Weiqi/Baduk) player rankings, ratings, and game history from goratings.org.

## Overview

GoRatings.org is a comprehensive database of professional Go players, providing:
- Overall player rankings based on Elo rating system
- Historical ladies top-3 rankings (1986 to present)
- Individual player profiles with game history
- Historical rating data for trend analysis

## Functions

### get_rankings

Fetch the overall player rankings.

**Parameters:**
- `language` (string, optional): Page language code. Default: `en`. Options: `en`, `zh`, `ja`, `ko`
- `limit` (integer, optional): Limit the number of players returned

**Example:**
```python
result = await execute({
    'function': 'get_rankings',
    'limit': 20
})
```

**Returns:**
```json
{
  "success": true,
  "rankings": [
    {
      "rank": 1,
      "name": "Shin Jinseo",
      "player_id": "1313",
      "gender": "♂",
      "country": "",
      "elo": 3873
    }
  ],
  "total_count": 20,
  "site_stats": {
    "games": "179383",
    "players": "2391",
    "most_recent_game": "2026-06-20"
  }
}
```

### get_ladies_rankings

Fetch historical ladies top-3 rankings. This returns the top 3 women players for each year from 1986 to present.

**Parameters:**
- `language` (string, optional): Page language code. Default: `en`

**Example:**
```python
result = await execute({
    'function': 'get_ladies_rankings'
})
```

**Returns:**
```json
{
  "success": true,
  "historical_rankings": [
    {
      "date": "2026-01-01",
      "top_3": [
        {"rank": 1, "name": "Yu Zhiying", "player_id": "1225"},
        {"rank": 2, "name": "Choi Jeong", "player_id": "1259"},
        {"rank": 3, "name": "Wu Yiming", "player_id": "2049"}
      ]
    }
  ],
  "total_years": 40
}
```

### get_player_info

Get detailed information about a specific player.

**Parameters:**
- `player_id` (string, required): Player ID (e.g., "1225")
- `language` (string, optional): Page language code. Default: `en`
- `include_history` (boolean, optional): Include rating history data. Default: `false`

**Example:**
```python
result = await execute({
    'function': 'get_player_info',
    'player_id': '1225',
    'include_history': true
})
```

**Returns:**
```json
{
  "success": true,
  "player": {
    "name": "Yu Zhiying",
    "player_id": "1225",
    "stats": {
      "wins": 577,
      "losses": 315,
      "total_games": 892
    },
    "recent_games": [
      {
        "date": "2026-06-17",
        "rating": "3286",
        "color": "White",
        "result": "Win",
        "opponent": "Xu Haizhe",
        "opponent_rating": 3049
      }
    ],
    "rating_history": [...]
  }
}
```

### get_player_rating_history

Fetch a player's complete rating history for charting.

**Parameters:**
- `player_id` (string, required): Player ID

**Example:**
```python
result = await execute({
    'function': 'get_player_rating_history',
    'player_id': '1313'
})
```

**Returns:**
```json
{
  "success": true,
  "player_id": "1313",
  "history": [
    {
      "name": "Rating",
      "data_points": 892,
      "values": [
        ["2010-2-21", 3152.58],
        ["2010-9-2", 3160.92]
      ]
    }
  ]
}
```

### get_ladies_history

Fetch historical ladies rating data for multiple top players (from JSON API). This provides detailed rating progressions for top women players over time.

**Example:**
```python
result = await execute({
    'function': 'get_ladies_history'
})
```

**Returns:**
```json
{
  "success": true,
  "players": [
    {
      "name": "Kobayashi Koichi",
      "data_points": 249,
      "values": [["1980-1-10", 3265.93], ...]
    }
  ],
  "total_count": 20
}
```

### search_player

Search for a player by name.

**Parameters:**
- `name` (string, required): Player name to search for (case-insensitive partial match)
- `language` (string, optional): Page language code. Default: `en`
- `limit` (integer, optional): Limit scanning range for quicker results

**Example:**
```python
result = await execute({
    'function': 'search_player',
    'name': 'Shin'
})
```

**Returns:**
```json
{
  "success": true,
  "query": "shin",
  "matches": [
    {
      "rank": 1,
      "name": "Shin Jinseo",
      "player_id": "1313",
      "gender": "♂",
      "elo": 3873
    }
  ],
  "match_count": 1
}
```

## Data Sources

The skill fetches data from:
- HTML pages for rankings and player profiles
- JSON endpoints for rating history data (e.g., `/players-json/data-{id}.json`, `/ladies-json/history.json`)

## Notes

- Player ratings are based on the Elo rating system
- The database includes over 2,000 professional players
- Data is updated regularly with recent tournament results
- Historical data spans many years of professional play
- Ladies rankings show historical top 3 by year (not current rankings)
- For current player ratings, use `get_player_info` or search by name