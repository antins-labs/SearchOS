# Douban Movie API Skill

Extract structured movie information from Douban's mobile API.

## Overview

This skill provides access to Douban movie data through their public mobile API at `m.douban.com`. The API returns JSON data with comprehensive movie information including ratings, cast, crew, plot summaries, and user reviews.

## Features

- **Movie Details**: Title (Chinese and original), rating, genres, countries, languages, duration, release dates, plot summary
- **Rating Statistics**: Vote distribution, wish list count, watched count, genre rankings
- **Cast & Crew**: Directors, actors, writers, producers with character names and profile links
- **User Reviews**: Popular and latest reviews with ratings and user information
- **Comprehensive Fetch**: All data in a single call with `get_full`

## API Endpoints

The skill uses Douban's Reykjavik (rexxar) mobile API:

- `GET /rexxar/api/v2/movie/{id}` - Basic movie info
- `GET /rexxar/api/v2/movie/{id}/rating` - Rating statistics
- `GET /rexxar/api/v2/movie/{id}/credits` - Cast and crew
- `GET /rexxar/api/v2/movie/{id}/interests` - User reviews

## Functions

### get_detail

Get basic movie information.

**Parameters:**
- `movie_id` (required): Douban movie ID or URL

**Returns:**
```json
{
  "success": true,
  "data": {
    "id": "27199894",
    "title": "超级马力欧兄弟大电影",
    "original_title": "The Super Mario Bros. Movie",
    "rating": {
      "score": 7.8,
      "max": 10,
      "star_count": 4.0,
      "vote_count": 165587
    },
    "directors": [{"name": "亚伦·霍瓦斯"}],
    "actors": [{"name": "克里斯·帕拉特"}, ...],
    "genres": ["喜剧", "动画", "奇幻"],
    "countries": ["美国", "日本"],
    "intro": "...",
    "poster": "https://..."
  }
}
```

### get_rating

Get rating statistics and distribution.

**Parameters:**
- `movie_id` (required): Douban movie ID or URL

**Returns:**
```json
{
  "success": true,
  "data": {
    "wish_count": 41420,
    "done_count": 196269,
    "rating_distribution": {
      "1_star": 0.41,
      "2_star": 3.25,
      "3_star": 28.96,
      "4_star": 42.79,
      "5_star": 24.59
    },
    "type_ranks": [
      {"type": "喜剧片", "rank_percentile": 0.93}
    ]
  }
}
```

### get_credits

Get detailed cast and crew information.

**Parameters:**
- `movie_id` (required): Douban movie ID or URL

**Returns:**
```json
{
  "success": true,
  "data": {
    "directors": [{"name": "詹姆斯·古恩", "latin_name": "James Gunn", ...}],
    "actors": [{"name": "克里斯·帕拉特", "character": "Actor (饰 星爵)", ...}],
    "writers": [...],
    "producers": [...],
    "total_count": 50
  }
}
```

### get_reviews

Get user reviews and comments.

**Parameters:**
- `movie_id` (required): Douban movie ID or URL
- `start` (optional, default: 0): Pagination offset
- `count` (optional, default: 10): Number of reviews (max 50)
- `order_by` (optional, default: "hot"): Sort by "hot" or "latest"

**Returns:**
```json
{
  "success": true,
  "data": {
    "total": 62306,
    "reviews": [
      {
        "id": "3744000784",
        "comment": "剧本也就是ChatGPT的水平。",
        "rating": 3,
        "star_count": 3,
        "vote_count": 3093,
        "user": {"name": "第六生", ...}
      }
    ]
  }
}
```

### get_full

Get comprehensive movie data (all endpoints in parallel).

**Parameters:**
- `movie_id` (required): Douban movie ID or URL

**Returns:**
```json
{
  "success": true,
  "data": {
    "detail": {...},
    "rating_stats": {...},
    "credits": {...},
    "top_reviews": {...}
  }
}
```

## Usage Examples

### Extract movie ID from URL

The skill automatically extracts movie IDs from various URL formats:

```python
# All of these work:
"https://m.douban.com/movie/subject/27199894/"
"https://movie.douban.com/subject/27199894/"
"27199894"
```

### Get movie information

```python
result = await execute({
    "function": "get_detail",
    "movie_id": "27199894"
})

if result["success"]:
    movie = result["data"]
    print(f"{movie['title']} - Rating: {movie['rating']['score']}/10")
```

### Get comprehensive data

```python
result = await execute({
    "function": "get_full",
    "movie_id": "https://m.douban.com/movie/subject/26258779/"
})

if result["success"]:
    data = result["data"]
    print(f"Title: {data['detail']['title']}")
    print(f"Director: {data['credits']['directors'][0]['name']}")
    print(f"Rating: {data['detail']['rating']['score']}")
    print(f"Reviews: {data['top_reviews']['total']}")
```

### Get user reviews

```python
result = await execute({
    "function": "get_reviews",
    "movie_id": "27199894",
    "count": 20,
    "order_by": "hot"
})

if result["success"]:
    for review in result["data"]["reviews"]:
        print(f"{review['user']['name']} ({review['rating']}★): {review['comment'][:50]}...")
```

## Notes

- **Language**: All text content is primarily in Chinese
- **Rating Scale**: Uses a 10-point scale internally, displayed as 5 stars in the UI
- **No Authentication**: The mobile API is publicly accessible
- **Rate Limiting**: Be respectful with request frequency (recommended: 2 requests/second)
- **Data Freshness**: Rating counts and reviews are updated in real-time

## Error Handling

The skill returns structured errors rather than raising exceptions:

```json
{
  "success": false,
  "error": "Movie not found",
  "code": 404
}
```

Common error cases:
- Invalid movie ID
- Movie ID not found (404)
- Network errors
- Rate limiting

## Data Sources

All data is sourced from Douban's mobile API:
- Base URL: `https://m.douban.com/rexxar/api/v2/movie/`
- API Version: v2
- Response Format: JSON