# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# IMDb Access Skill via r.jina.ai

This skill fetches and parses IMDb content through the r.jina.ai reader service, which renders JavaScript-heavy pages into readable markdown format.

## Features

- **Movie/TV Show Extraction**: Get detailed information about movies and TV shows including title, rating, genres, cast, crew, storyline, and release details
- **List Extraction**: Extract all items from IMDb lists with titles, ranks, ratings, and years
- **Person/Name Extraction**: Get information about actors, directors, and other film industry professionals including their known works and filmography

## Usage

### Get Movie Information

Extract detailed information about a movie or TV show:

```python
# Using full URL
params = {
    "function": "get_movie",
    "url": "http://www.imdb.com/title/tt0185906/"
}

# Or using just the IMDb ID
params = {
    "function": "get_movie",
    "url": "tt0185906"
}
```

Returns:
- `title`: Movie/TV show title
- `year_info`: Year or year range
- `rating`: IMDb rating (0-10)
- `genres`: List of genres
- `creators`: List of creators (for TV shows)
- `directors`: List of directors
- `stars`: List of main cast members
- `storyline`: Plot summary
- `details`: Release date, countries, languages

### Get List Items

Extract items from an IMDb list:

```python
params = {
    "function": "get_list",
    "url": "http://www.imdb.com/list/ls033953812/"
}

# Or using just the list ID
params = {
    "function": "get_list",
    "url": "ls033953812"
}
```

Returns:
- `title`: List title
- `description`: List description
- `total_items`: Total number of items in list
- `items`: Array of list items with:
  - `rank`: Position in list
  - `title`: Item title
  - `imdb_id`: IMDb ID (ttXXXXXX)
  - `url`: IMDb URL
  - `year`: Year or year range
  - `rating`: IMDb rating
  - `type`: Type (Movie, TV Series, etc.)

### Get Person Information

Extract information about an actor, director, or other film professional:

```python
params = {
    "function": "get_name",
    "url": "http://www.imdb.com/name/nm0000410/"
}

# Or using just the person ID
params = {
    "function": "get_name",
    "url": "nm0000410"
}
```

Returns:
- `name`: Person's name
- `known_for`: Array of notable works
- `filmography`: Array of film/TV credits

## Technical Details

- Uses Playwright to access r.jina.ai which renders IMDb pages into markdown
- Handles JavaScript-heavy content that direct HTTP requests cannot parse
- Supports all IMDb URL formats and ID-only inputs
- Extracts structured data from unstructured markdown output

## Limitations

- Search functionality is not supported (r.jina.ai doesn't provide search)
- Requires specific IMDb URLs or IDs
- Performance depends on r.jina.ai service availability
- Some complex page layouts may not parse perfectly

## Example Results

### Movie Example (Band of Brothers)
```json
{
  "success": true,
  "type": "movie",
  "title": "Band of Brothers",
  "year_info": "TV Mini Series 2001",
  "rating": 9.4,
  "genres": ["Action", "Drama", "History"],
  "creators": [{"name": "Tom Hanks", "imdb_id": "nm0000158"}],
  "stars": [
    {"name": "Scott Grimes", "imdb_id": "nm0342241"},
    {"name": "Damian Lewis", "imdb_id": "nm0507073"}
  ]
}
```

### List Example (Top 100 TV Shows)
```json
{
  "success": true,
  "type": "list",
  "title": "Top 100 TV Shows as Rated by Women on IMDb in 2016",
  "total_items": 100,
  "items_count": 100,
  "items": [
    {
      "rank": 1,
      "title": "Band of Brothers",
      "imdb_id": "tt0185906",
      "year": "2001",
      "rating": 9.4
    }
  ]
}
```

## Error Handling

The skill returns structured error messages:
- Invalid URL format: Returns error with guidance
- Network failures: Returns error with details
- Missing content: Returns partial results with available data
