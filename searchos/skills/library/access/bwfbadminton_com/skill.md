# BWF Badminton Fansite Access Skill

This skill accesses the official Badminton World Federation (BWF) fansite data through the extranet API at `extranet-lv.bwfbadminton.com`.

## Overview

The BWF fansite provides comprehensive badminton player and tournament data, but the main website may fail with HTTP errors. This skill directly accesses the underlying API endpoints to reliably fetch:

- Player profiles and biographies
- Match history and results
- Upcoming match schedules  
- Photo galleries
- Related news articles

## Player ID Reference

Some verified player IDs for testing:

| Player | ID | Country |
|--------|-----|---------|
| LIN Dan (林丹) | 50906 | China |
| CHEN Long (谌龙) | 75787 | China |
| Kunlavut VITIDSARN | 64032 | Thailand |
| Pernille AABEL SORENSEN | 50873 | Denmark |
| Lars KURE | 52397 | Denmark |

**Note:** Player IDs in the BWF system may not correspond to well-known external databases. Always verify player IDs using the `search_player_by_id` function or by finding them in match results.

## API Endpoints Used

The skill uses the following BWF extranet API endpoints:

1. **vue-player-summary** - Basic player info, nationality, avatar
2. **vue-player-bio** - Detailed biography, height, age, prize money
3. **vue-player-match-previous** - Historical match results with scores
4. **vue-player-match-next** - Upcoming match schedule
5. **vue-player-gallery** - Photo gallery images
6. **vue-player-news** - Related news articles (via WordPress internal API)

## Functions

### get_player_summary

Fetch a player's basic profile information.

**Parameters:**
- `player_id`: BWF player ID (integer)

**Returns:**
```json
{
  "success": true,
  "data": {
    "player_id": 50906,
    "name": "LIN Dan",
    "country": {"name": "China", "code_iso3": "CHN"},
    "date_of_birth": "1983-10-14 00:00:00",
    "avatar": "https://...",
    "bio": {
      "height": "178.00",
      "languages": "Chinese",
      "equipment_sponsor": "YONEX",
      "current_residence": "Beijing, China",
      "memorable_achievements": "Beijing 2008 Olympic Champion...",
      ...
    }
  }
}
```

### get_player_bio

Fetch detailed player biography.

**Parameters:**
- `player_id`: BWF player ID (integer)

**Returns:**
```json
{
  "success": true,
  "data": {
    "player_id": 50906,
    "height": "178",
    "age": 42,
    "playing_hand": "Left",
    "current_residence": "Beijing, China",
    "prize_money": "1,049,243",
    "social": {
      "instagram": "",
      "twitter": "http://t.qq.com/superdan"
    }
  }
}
```

### get_player_previous_matches

Fetch player's match history.

**Parameters:**
- `player_id`: BWF player ID (integer)
- `limit`: Number of matches to fetch (optional, default 10)

**Returns:**
```json
{
  "success": true,
  "data": {
    "matches": [
      {
        "match_id": 1213679,
        "match_time": "2020-03-12 15:30:00",
        "round": "R16",
        "duration_minutes": 45,
        "winner": 2,
        "score": {
          "team1": "<span>17</span><span>8</span>",
          "team2": "<span>21</span><span>21</span>"
        },
        "tournament": {
          "id": 3690,
          "name": "YONEX All England Open 2020",
          "slug": "yonex-all-england-open-2020",
          "url": "https://bwfworldtour.bwfbadminton.com/..."
        },
        "draw": "MS",
        "team1": {
          "player1": {
            "id": 50906,
            "name": "LIN Dan",
            "country": "China",
            "country_code": "CHN"
          }
        },
        "team2": {
          "player1": {
            "id": 75787,
            "name": "CHEN Long",
            "country": "China",
            "country_code": "CHN"
          }
        }
      }
    ],
    "count": 1
  }
}
```

### get_player_next_match

Fetch upcoming match schedule.

**Parameters:**
- `player_id`: BWF player ID (integer)

**Returns:** Match info or `{success: true, data: {match: null, message: "No upcoming match scheduled"}}`

### get_player_gallery

Fetch player's photo gallery.

**Parameters:**
- `player_id`: BWF player ID (integer)

### get_player_news

Fetch news articles mentioning the player.

**Parameters:**
- `player_id`: BWF player ID (integer)

### get_player_full_profile

Fetch complete player profile in a single call (summary + bio + matches + next match).

**Parameters:**
- `player_id`: BWF player ID (integer)

### search_player_by_id

Verify a player ID exists and return basic info.

**Parameters:**
- `player_id`: BWF player ID (integer)

## Notes

1. **Score Format**: Match scores are returned as HTML spans (e.g., `<span>21</span><span>15</span>`). Parse the numbers for display.

2. **Winner Field**: In match data:
   - `winner: 1` = team1 (the queried player) won
   - `winner: 2` = team2 (opponent) won

3. **Draw Types**: The `draw` field indicates event category:
   - MS = Men's Singles
   - WS = Women's Singles  
   - MD = Men's Doubles
   - WD = Women's Doubles
   - XD = Mixed Doubles

4. **API Caching**: The API returns cached data. Repeated requests for the same player may show identical results.

5. **Retired Players**: Retired players (like LIN Dan) have full historical data but no upcoming matches.

6. **Tournament Links**: Match data includes tournament URLs that may point to different subdomains (bwfworldtour.bwfbadminton.com) which may require separate handling.

## Examples

### Get LIN Dan's full profile
```python
result = await execute({
    "function": "get_player_full_profile",
    "player_id": 50906
})
```

### Get last 5 matches for Kunlavut Vitidsarn
```python
result = await execute({
    "function": "get_player_previous_matches",
    "player_id": 64032,
    "limit": 5
})
```

### Verify a player ID exists
```python
result = await execute({
    "function": "search_player_by_id",
    "player_id": 75787
})
# Returns: {"success": true, "data": {"name": "CHEN Long", "country": "China", ...}}
```