# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Bob Dylan Official Site - Discography Access Skill

Access Bob Dylan's official album discography from www.bobdylan.com.

## Features

### List Albums (`list_albums`)
Retrieve Bob Dylan's discography with optional filtering:
- **chronological**: Albums in chronological order (from 1962 debut to latest)
- **studio**: Studio albums only
- **live**: Live albums and recordings
- **compilations**: Compilation albums
- **bootleg**: The Bootleg Series releases
- **all**: All albums (default, shows newest first)
- **a-z**: Alphabetical order

**Example:**
```json
{
  "function": "list_albums",
  "filter": "studio"
}
```

Returns album titles, URLs, and slugs for further detail queries.

### Get Album Details (`get_album`)
Retrieve detailed information about a specific album including:
- Album title and release year
- Cover art URL
- Complete track listing with song URLs
- Purchase links (Amazon, iTunes, etc.)

**Using album slug:**
```json
{
  "function": "get_album",
  "album_slug": "blonde-on-blonde"
}
```

**Using full URL:**
```json
{
  "function": "get_album",
  "album_url": "https://www.bobdylan.com/albums/fallen-angels/"
}
```

## Data Structure

### Album List Response
```json
{
  "success": true,
  "filter": "studio",
  "count": 40,
  "albums": [
    {
      "title": "Rough and Rowdy Ways",
      "url": "https://www.bobdylan.com/albums/rough-and-rowdy-ways/",
      "slug": "rough-and-rowdy-ways"
    }
  ]
}
```

### Album Detail Response
```json
{
  "success": true,
  "album": {
    "title": "Blonde on Blonde",
    "year": 1966,
    "headline": "Blonde on Blonde (1966)",
    "slug": "blonde-on-blonde",
    "url": "https://www.bobdylan.com/albums/blonde-on-blonde/",
    "cover_url": "https://cdn-p.smehost.net/...",
    "track_count": 14,
    "tracks": [
      {
        "number": 1,
        "title": "Rainy Day Women #12 & 35",
        "full_title": "1. Rainy Day Women #12 & 35",
        "url": "https://www.bobdylan.com/songs/rainy-day-women-12-35/"
      }
    ],
    "purchase_options": [
      {
        "platform": "Amazon",
        "url": "http://www.smarturl.it/..."
      }
    ]
  }
}
```

## Notes

- The site uses JavaScript rendering, so this skill uses Playwright browser automation
- Album URLs follow the pattern: `https://www.bobdylan.com/albums/{slug}/`
- Track URLs link to individual song pages on www.bobdylan.com
- Purchase links redirect to external platforms (Amazon, iTunes, etc.)
- Some albums may have limited purchase options depending on availability

## Common Album Slugs

Popular albums and their slugs for quick reference:
- `bob-dylan` - Bob Dylan (1962)
- `freewheelin-bob-dylan` - The Freewheelin' Bob Dylan (1963)
- `blonde-on-blonde` - Blonde on Blonde (1966)
- `blood-on-the-tracks` - Blood on the Tracks (1975)
- `rough-and-rowdy-ways` - Rough and Rowdy Ways (2020)
- `fallen-angels` - Fallen Angels (2016)
- `tempest` - Tempest (2012)
