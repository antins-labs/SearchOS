# Wikipedia Billionaires Access Skill

This skill extracts structured billionaire ranking data from Wikipedia's "[The World's Billionaires](https://en.wikipedia.org/wiki/The_World%27s_Billionaires)" page.

## Overview

The page contains annual Forbes magazine rankings of the world's wealthiest people, organized in wikitable format from 1990 to present. Each year's table includes:
- Rank
- Name (with Wikipedia link)
- Net worth (USD)
- Age
- Nationality
- Primary source(s) of wealth

## Functions

### `get_billionaires`

Get billionaire rankings for a specific year or all years.

**Parameters:**
- `year` (optional): Specific year like "2024". If omitted, returns summary for all years.
- `rank_limit` (optional): Max billionaires per year (default: 10, max: 100)

**Example - Get 2024 rankings:**
```json
{
  "function": "get_billionaires",
  "year": "2024",
  "rank_limit": 5
}
```

**Response:**
```json
{
  "year": "2024",
  "count": 10,
  "headers": ["No.", "Name", "Net worth (USD)", "Age", "Nationality", "Primary source(s) of wealth"],
  "billionaires": [
    {
      "No.": "1",
      "Name": "Bernard Arnault & family",
      "Net worth (USD)": "$233 billion",
      "net_worth_billions": 233.0,
      "Age": "75",
      "Nationality": "France",
      "Primary source(s) of wealth": "LVMH",
      "wikipedia_url": "https://en.wikipedia.org/wiki/Bernard_Arnault"
    },
    ...
  ]
}
```

### `search_billionaire`

Search for a billionaire by name across all years.

**Parameters:**
- `name` (required): Name to search for (partial match, case-insensitive)
- `limit` (optional): Max results per year (default: 3, max: 10)
- `max_years` (optional): Max years to search

**Example - Search for "Musk":**
```json
{
  "function": "search_billionaire",
  "name": "musk"
}
```

**Response:**
```json
{
  "query": "musk",
  "found": true,
  "years_with_matches": 8,
  "results": [
    {
      "year": "2026",
      "matches": [
        {
          "year": "2026",
          "rank": "1",
          "name": "Elon Musk",
          "net_worth": "$839 billion",
          "net_worth_billions": 839.0,
          "age": "54",
          "nationality": "United States",
          "source": "Tesla and SpaceX",
          "wikipedia_url": "https://en.wikipedia.org/wiki/Elon_Musk"
        }
      ],
      "total_matches": 1
    },
    ...
  ]
}
```

### `get_years`

Get list of all available years.

**Example:**
```json
{
  "function": "get_years"
}
```

**Response:**
```json
{
  "years": ["1990", "1991", ..., "2024", "2025", "2026"],
  "total_years": 37,
  "year_range": {
    "earliest": "1990",
    "latest": "2026"
  },
  "years_info": [
    {"year": "1990", "billionaire_count": 10, "top_billionaire": "..."},
    ...
  ]
}
```

## Data Notes

- **Years covered**: 1990 through current year (2026 as of latest data)
- **Billionaires per year**: Typically top 10, some years have more
- **Net worth parsing**: The `net_worth_billions` field provides a numeric value extracted from the display string
- **Wikipedia links**: Extracted from the Name column when available
- **Historical changes**: Column headers may vary slightly across years (e.g., "Source(s) of wealth" vs "Primary source(s) of wealth")

## Error Handling

All functions return an `error` field on failure:

```json
{
  "error": "Year 1985 not found. Available years: ['1990', '1991', ...]"
}
```

Search returns `found: false` for no matches:

```json
{
  "query": "nonexistent person",
  "found": false,
  "message": "No billionaires found matching \"nonexistent person\""
}
```

## Implementation Notes

- Uses direct HTTP requests with proper User-Agent headers
- Parses HTML with BeautifulSoup
- No browser automation required
- Respects Wikipedia's rate limiting guidelines