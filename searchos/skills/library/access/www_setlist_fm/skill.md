# Setlist.fm Access Skill

This skill extracts concert setlist data from [setlist.fm](https://www.setlist.fm), the world's largest platform for concert setlists.

## Features

### Get Specific Setlist
Fetch complete setlist data for a specific concert, including:
- Concert date and venue information
- Artist name and event/festival name
- Complete song listing with order
- Song metadata (covers, guests, set divisions)
- Tour information

### Get Average Setlist
Fetch the average/typical setlist for an artist or specific tour:
- Artist-level typical setlist
- Tour-specific setlist filtering
- Song ordering based on most common performances

## Usage

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `function` | string | Yes | Function to call: `get_setlist` or `get_average_setlist` |
| `setlist_url` | string | For `get_setlist` | URL of a specific concert setlist page |
| `average_setlist_url` | string | For `get_average_setlist` | URL of an average setlist page (can include `tour` query parameter) |

### Examples

#### Get a specific concert setlist
```python
result = await execute({
    'function': 'get_setlist',
    'setlist_url': 'https://www.setlist.fm/setlist/taylor-swift/2010/chiba-marine-stadium-chiba-japan-23c544ff.html'
})
```

#### Get average setlist for an artist
```python
result = await execute({
    'function': 'get_average_setlist',
    'average_setlist_url': 'https://www.setlist.fm/stats/average-setlist/taylor-swift-3bd6bc5c.html'
})
```

#### Get average setlist for a specific tour
```python
result = await execute({
    'function': 'get_average_setlist',
    'average_setlist_url': 'https://www.setlist.fm/stats/average-setlist/taylor-swift-3bd6bc5c.html?tour=bd6adba'
})
```

## Return Values

### Success Response
```json
{
  "success": true,
  "type": "setlist" | "average_setlist",
  "data": {
    "title": "Taylor Swift Concert Setlist at...",
    "artist": "Taylor Swift",
    "h1": "Taylor Swift Setlist at Chiba Marine Stadium, Chiba, Japan",
    "url": "https://...",
    "date": "Aug 8 2010",
    "venue": {
      "name": "Chiba Marine Stadium, Chiba, Japan",
      "url": "https://...",
      "id": "bd62d02"
    },
    "event": {
      "name": "SUMMER SONIC 2010 Tokyo",
      "url": "https://..."
    },
    "tour": {
      "name": "Fearless Tour",
      "url": "..."
    },
    "songs": [
      {
        "position": 1,
        "name": "You Belong With Me",
        "song_id": "3d7f1f7",
        "set": null,
        "is_cover": false,
        "with_guest": false,
        "info": null,
        "stats_url": "https://..."
      }
    ],
    "total_songs": 10
  }
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error message",
  "error_type": "validation|timeout|..."
}
```

## Song Metadata

Each song in the setlist includes:
- `position`: Order in the setlist
- `name`: Song title
- `song_id`: setlist.fm's unique song identifier
- `set`: Set name if part of a multi-set show (e.g., "Encore", "Acoustic Set")
- `is_cover`: Boolean indicating if it's a cover song
- `with_guest`: Boolean indicating if performed with a guest artist
- `info`: Additional notes about the performance
- `stats_url`: Link to song statistics on setlist.fm

## Technical Notes

This skill uses Playwright (headless browser) to fetch pages because setlist.fm employs AWS WAF protection that requires JavaScript execution to bypass. Direct HTTP requests return a 202 challenge response.

## Data Sources

All data comes from [setlist.fm](https://www.setlist.fm), a community-driven platform where users contribute and verify concert setlists.