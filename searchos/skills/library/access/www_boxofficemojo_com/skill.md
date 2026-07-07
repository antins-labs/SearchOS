# Box Office Mojo Access Skill

Access yearly box office data from Box Office Mojo (www.boxofficemojo.com), including movie rankings, domestic gross revenue, theater counts, release dates, and distributor information.

## Overview

Box Office Mojo is a comprehensive box office tracking website owned by IMDb (Amazon). This skill provides structured access to:

- Yearly domestic box office rankings
- Gross revenue figures
- Theater counts
- Release dates
- Distributor information
- Individual movie details

## Functions

### `get_yearly_box_office`

Retrieve complete box office data for a specific year.

**Parameters:**
- `year` (integer, required): The year to retrieve data for

**Example:**
```python
result = await execute({
    'function': 'get_yearly_box_office',
    'year': 2024
})
```

**Response:**
```json
{
    "success": true,
    "year": 2024,
    "url": "https://www.boxofficemojo.com/year/2024/",
    "total_movies": 200,
    "total_gross_domestic": "$4,346,543,010",
    "movies": [
        {
            "rank": 1,
            "title": "Inside Out 2",
            "release_id": "rl3638199041",
            "url": "https://www.boxofficemojo.com/release/rl3638199041/",
            "gross_domestic": "$652,980,194",
            "gross_domestic_cents": 65298019400,
            "gross_total": "$652,980,194",
            "theaters": 4440,
            "release_date": "2024-06-14",
            "distributor": "Walt Disney Studios Motion Pictures",
            "year": 2024
        }
    ]
}
```

### `list_top_movies`

List the top N movies for a given year.

**Parameters:**
- `year` (integer, required): The year to retrieve data for
- `count` (integer, optional): Number of movies to return (default: 10, max: 200)

**Example:**
```python
result = await execute({
    'function': 'list_top_movies',
    'year': 2023,
    'count': 5
})
```

**Response:**
```json
{
    "success": true,
    "year": 2023,
    "count": 5,
    "movies": [
        {
            "rank": 1,
            "title": "Barbie",
            "gross_domestic": "$636,225,983",
            "theaters": 4337,
            "release_date": "2023-07-21",
            "distributor": "Warner Bros."
        }
    ]
}
```

### `get_movie_details`

Get detailed information about a specific movie release.

**Parameters:**
- `release_id` (string, required): The Box Office Mojo release ID (e.g., 'rl3638199041')

**Example:**
```python
result = await execute({
    'function': 'get_movie_details',
    'release_id': 'rl3638199041'
})
```

**Response:**
```json
{
    "success": true,
    "release_id": "rl3638199041",
    "url": "https://www.boxofficemojo.com/release/rl3638199041/",
    "title": "Inside Out 2 (2024)",
    "domestic_gross": "$652,980,194",
    "domestic_gross_cents": 65298019400,
    "worldwide_gross": "$1,697,335,296",
    "distributor": "Walt Disney Studios Motion Pictures",
    "release_date": "June 14, 2024",
    "genre": "Animation",
    "runtime": "1 hr 36 min",
    "rating": "PG"
}
```

## Data Notes

### Gross Revenue
- All monetary values are provided in both formatted strings (`$652,980,194`) and as integers in cents (`65298019400`) for precision
- The `gross_domestic` field represents US/Canada box office revenue
- The `gross_total` field may differ from domestic when international data is available

### Release Dates
- Dates are returned in ISO format (`YYYY-MM-DD`) when parseable
- For yearly data, dates like "Jun 14" are converted to the queried year

### Release IDs
- Release IDs (e.g., `rl3638199041`) are unique identifiers used by Box Office Mojo
- These can be extracted from the `get_yearly_box_office` response
- Use these IDs with `get_movie_details` for more information

### Ranking
- Rankings are based on domestic gross revenue
- The site typically shows up to 200 movies per year

## Error Handling

All functions return a consistent error structure:

```json
{
    "success": false,
    "error": "Description of the error",
    "available_functions": ["get_yearly_box_office", "list_top_movies", "get_movie_details"]
}
```

Common errors:
- Missing required parameters
- Invalid year or count values
- Network/timeout errors
- Release ID not found

## Technical Implementation

This skill:
- Uses `aiohttp` for HTTP requests (no browser automation)
- Parses HTML with `BeautifulSoup4`
- Handles server-side rendered tables from Box Office Mojo
- respects the site's HTML structure with CSS class selectors
- Provides both human-readable and machine-precise data formats