# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Rotten Tomatoes Access Skill

Fetches comprehensive movie and TV show information from Rotten Tomatoes.

## Features

- **Tomatometer**: Critics score with review count, average rating, and certification status
- **Audience Score**: Popcornmeter with verified ratings, like/dislike counts
- **Cast & Crew**: Actors, directors, and producers with profile links
- **TV Shows**: Season information, episode lists with air dates
- **Metadata**: Genres, content rating, runtime, release date, trailer links

## Functions

### get_movie

Get detailed information about a movie.

**Parameters:**
- `vanity` (required): Movie vanity name or full URL

**Example:**
```json
{
  "function": "get_movie",
  "vanity": "oppenheimer_2023"
}
```

Or with full URL:
```json
{
  "function": "get_movie",
  "vanity": "https://www.rottentomatoes.com/m/oppenheimer_2023"
}
```

**Returns:**
```json
{
  "success": true,
  "type": "Movie",
  "title": "Oppenheimer (2023)",
  "tomatometer": {
    "score": "93",
    "review_count": 509,
    "average_rating": "8.60",
    "sentiment": "POSITIVE",
    "certified": true
  },
  "audience_score": {
    "score": "91",
    "review_count": 6024,
    "average_rating": "4.5",
    "sentiment": "POSITIVE",
    "certified": true
  },
  "cast": [...],
  "directors": [...],
  "genres": ["Biography", "History", "Drama"],
  "content_rating": "R",
  ...
}
```

### get_tv_show

Get information about a TV show, optionally for a specific season.

**Parameters:**
- `vanity` (required): TV show vanity name or full URL
- `season` (optional): Season identifier like "s01", "s02"

**Examples:**
```json
{
  "function": "get_tv_show",
  "vanity": "the_last_of_us"
}
```

```json
{
  "function": "get_tv_show",
  "vanity": "the_last_of_us",
  "season": "s01"
}
```

**Returns:** Similar to movie but includes seasons list or episode details.

### get_seasons

Get list of all seasons for a TV show.

**Parameters:**
- `vanity` (required): TV show vanity name or full URL

**Example:**
```json
{
  "function": "get_seasons",
  "vanity": "stranger_things"
}
```

**Returns:**
```json
{
  "success": true,
  "vanity": "stranger_things",
  "title": "Stranger Things",
  "number_of_seasons": 5,
  "seasons": [
    {"name": "Season 5", "url": "...", "season_id": "s05"},
    {"name": "Season 4", "url": "...", "season_id": "s04"},
    ...
  ]
}
```

### get_by_url

Auto-detect media type from URL and fetch information.

**Parameters:**
- `url` (required): Full Rotten Tomatoes URL

**Example:**
```json
{
  "function": "get_by_url",
  "url": "https://www.rottentomatoes.com/tv/the_last_of_us/s01"
}
```

## Data Sources

The skill extracts data from:
1. **JSON-LD structured data**: Standard Schema.org metadata for movies/TV shows
2. **Embedded JavaScript**: Detailed score information including audience ratings

## Notes

- Vanity names are the URL identifiers (e.g., "oppenheimer_2023", "the_last_of_us")
- For movies, URLs use `/m/{vanity}` format
- For TV shows, URLs use `/tv/{vanity}` format
- Season URLs add `/{season}` (e.g., `/tv/the_last_of_us/s01`)
- The skill handles redirects and 404 pages gracefully
- Some shows may not have audience scores available
