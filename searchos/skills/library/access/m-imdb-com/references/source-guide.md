# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# IMDB Movie/TV Show Data Extractor

Extracts comprehensive metadata from IMDB title pages, including movies, TV shows, and other content types.

## Features

- **Reliable Extraction**: Uses JSON-LD structured data embedded in IMDB pages for consistent, accurate results
- **Handles Redirects**: Automatically follows m.imdb.com → www.imdb.com redirects
- **Anti-Bot Handling**: Uses browser automation to handle JavaScript rendering and anti-bot measures
- **Comprehensive Data**: Extracts title, year, rating, genres, cast, directors, writers, duration, description, trailer, and more

## Supported URL Formats

- `https://www.imdb.com/title/tt0133093/`
- `https://m.imdb.com/title/tt0133093/`
- Any IMDB title URL (movies, TV series, episodes, etc.)

## Functions

### get_movie

Fetches and parses metadata from an IMDB title page.

**Parameters:**
- `url` (required): IMDB title URL
- `timeout_ms` (optional): Navigation timeout in milliseconds (default: 60000)

**Returns:**

```json
{
  "success": true,
  "url": "https://www.imdb.com/title/tt0133093/",
  "data": {
    "title": "The Matrix",
    "type": "Movie",
    "url": "https://www.imdb.com/title/tt0133093/",
    "year": "1999",
    "date_published": "1999-03-31",
    "genres": ["Action", "Sci-Fi"],
    "rating": {
      "value": 8.7,
      "count": 2261022,
      "best": 10,
      "worst": 1
    },
    "content_rating": "R",
    "duration": {
      "hours": 2,
      "minutes": 16,
      "total_minutes": 136
    },
    "duration_iso": "PT2H16M",
    "directors": ["Lana Wachowski", "Lilly Wachowski"],
    "actors": ["Keanu Reeves", "Laurence Fishburne", "Carrie-Anne Moss"],
    "writers": ["Lilly Wachowski", "Lana Wachowski"],
    "description": "A computer hacker discovers that his life is nothing more than an elaborate simulation...",
    "image_url": "https://m.media-amazon.com/images/...",
    "keywords": ["war with machines", "artificial reality", ...],
    "trailer": {
      "name": "Theatrical Trailer",
      "url": "https://www.imdb.com/video/vi1032782617/",
      "embed_url": "https://www.imdb.com/video/vi1032782617/",
      "duration": "PT2M26S"
    }
  }
}
```

## Example Usage

```
Function: get_movie
URL: https://m.imdb.com/title/tt0770828/
```

Returns metadata for "Man of Steel" including rating (7.1), genres (Action, Adventure, Sci-Fi), cast (Henry Cavill, Amy Adams, Michael Shannon), director (Zack Snyder), and more.

## Error Handling

Returns structured error responses:

```json
{
  "success": false,
  "error": "No JSON-LD structured data found on page",
  "url": "https://www.imdb.com/title/tt0000000/"
}
```

## Notes

- The extractor uses Playwright browser automation to handle IMDB's anti-bot protection
- JSON-LD structured data provides reliable, schema.org-compliant metadata
- Duration is parsed from ISO 8601 format (PT2H16M) into hours, minutes, and total_minutes
- Actors list is limited to 15 entries, writers to 10, keywords to 20
