# Maoyan Box Office Access Skill

Access Chinese box office rankings and movie details from [piaofang.maoyan.com](https://piaofang.maoyan.com), the professional box office analysis platform by Maoyan (猫眼).

## Overview

This skill provides access to comprehensive Chinese box office data including:

- **Yearly Rankings**: Top movies by box office revenue for each year
- **All-Time Rankings**: Historical box office leaders across all years
- **Movie Details**: Comprehensive film information including cast, crew, technical specs, and release data

## Functions

### `get_rankings`

Get box office rankings with optional year filter.

**Parameters:**
- `year` (integer, optional): Year filter (e.g., 2024, 2023). If not provided, returns all-time rankings.
- `limit` (integer, optional): Limit on number of results to return.

**Example:**
```python
# Get all-time top 10
result = await execute({"function": "get_rankings", "limit": 10})

# Get 2024 rankings
result = await execute({"function": "get_rankings", "year": 2024})
```

**Returns:**
- `rank`: Position in rankings
- `name`: Movie title (Chinese)
- `movie_id`: Maoyan movie ID for detailed lookups
- `release_date`: Release date (YYYY-MM-DD)
- `box_office_wan`: Box office in 万元 (10,000 yuan units)
- `avg_price`: Average ticket price (yuan)
- `avg_people`: Average people per screening

### `get_movie_detail`

Get detailed information for a specific movie.

**Parameters:**
- `movie_id` (string, required): The Maoyan movie ID

**Example:**
```python
result = await execute({"function": "get_movie_detail", "movie_id": "1211229"})
```

**Returns:**
- `title`: Chinese title
- `english_title`: English title (if available)
- `genre`: Film genre
- `country`: Country of origin
- `duration`: Duration in minutes
- `release_date`: Release date
- `rating`: Preview/screening rating (if available)
- `directors`: List of directors
- `actors`: List of actors
- `writers`: List of writers
- `synopsis`: Film summary
- `technical_params`: Technical specifications (aspect ratio, color, etc.)

### `search_by_rank`

Search movies by rank criteria.

**Parameters:**
- `year` (integer, optional): Year filter
- `min_rank` (integer, optional): Minimum rank (inclusive)
- `max_rank` (integer, optional): Maximum rank (inclusive)

**Example:**
```python
# Get top 5 movies
result = await execute({"function": "search_by_rank", "min_rank": 1, "max_rank": 5})

# Get movies ranked 10-20 in 2024
result = await execute({
    "function": "search_by_rank",
    "year": 2024,
    "min_rank": 10,
    "max_rank": 20
})
```

## Data Notes

### Box Office Units
- Box office figures are reported in **万元** (wan yuan = 10,000 yuan)
- To convert to CNY: multiply by 10,000
- To convert to USD: multiply by 10,000 * exchange rate

### Available Years
- Historical data available from 2011 onwards
- Current year data is continuously updated
- Use `get_rankings` without year parameter for all-time rankings

### Movie IDs
- Found in the `movie_id` field of rankings results
- Used to fetch detailed movie information
- Format: numeric string (e.g., "1211229", "257706")

## Sample Output

### Rankings
```json
{
  "success": true,
  "data": {
    "total_count": 300,
    "rankings": [
      {
        "rank": 1,
        "name": "哪吒之魔童闹海",
        "movie_id": "1294273",
        "release_date": "2025-01-29",
        "box_office_wan": "1544614",
        "avg_price": "47.639984",
        "avg_people": "24"
      }
    ]
  }
}
```

### Movie Detail
```json
{
  "success": true,
  "data": {
    "movie": {
      "movie_id": "1211229",
      "title": "银翼杀手：2048无处可逃",
      "genre": "科幻",
      "country": "美国",
      "duration": 6,
      "release_date": "2017-09-14",
      "rating": 7.0,
      "directors": ["卢克·斯科特"],
      "actors": ["亚当·萨维奇", "戴夫·巴蒂斯塔"]
    }
  }
}
```

## Rate Limiting

To avoid overwhelming the server:
- Maximum 2 requests per second
- Maximum 30 requests per minute

## Technical Details

- Data is server-side rendered HTML (no API endpoints)
- Requires proper browser User-Agent headers
- Uses BeautifulSoup for HTML parsing
- All requests are async using aiohttp