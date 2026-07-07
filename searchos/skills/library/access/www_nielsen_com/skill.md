# Nielsen News Center Access Skill

Extract viewership metrics, ratings data, and Super Bowl historical statistics from Nielsen's official news articles.

## Overview

This skill provides programmatic access to Nielsen's News Center articles, with specialized extraction for TV viewership metrics and ratings data. It can extract structured data from articles including:
- Super Bowl historical viewership tables (60+ years of data)
- Household ratings and share metrics
- Peak audience measurements
- Broadcast network information
- Year-over-year comparisons

## Available Functions

### extract_article

Extracts complete article content with metrics from a specific Nielsen News Center URL.

**Parameters:**
- `url` (required): Full URL to the Nielsen article

**Returns:**
- Article headline, publication date, and content
- Embedded viewership metrics extracted from text
- Data tables (including Super Bowl historical data)
- Images and JSON-LD metadata

**Example:**
```python
params = {
    'function': 'extract_article',
    'url': 'https://www.nielsen.com/news-center/2025/super-bowl-lix-makes-tv-history-with-over-127-million-viewers/'
}
```

### search_articles

Searches the Nielsen News Center RSS feed for articles matching a query.

**Parameters:**
- `query` (required): Search term or keyword
- `max_results` (optional): Maximum number of results to return (default: 20)

**Returns:**
- List of matching articles with title, link, publication date, and description

**Example:**
```python
params = {
    'function': 'search_articles',
    'query': 'Super Bowl',
    'max_results': 10
}
```

### get_latest_articles

Retrieves the most recent articles from Nielsen's News Center.

**Parameters:**
- `limit` (optional): Maximum number of articles to return (default: 10)

**Returns:**
- List of latest articles with basic metadata

**Example:**
```python
params = {
    'function': 'get_latest_articles',
    'limit': 15
}
```

### get_super_bowl_data

Extracts comprehensive Super Bowl historical viewership data including 60+ years of ratings statistics.

**Parameters:**
- `url` (optional): Article URL containing Super Bowl data table. If not provided, uses the default Super Bowl LIX article which includes the full historical table.

**Returns:**
- Headline and publication date
- Super Bowl historical data with Super Bowl number, network(s), total viewers, household rating, and date for each game
- Current game metrics (viewers, rating, share, peak audience)

**Example:**
```python
params = {
    'function': 'get_super_bowl_data'
}
# or with specific URL
params = {
    'function': 'get_super_bowl_data',
    'url': 'https://www.nielsen.com/news-center/2025/super-bowl-lix-makes-tv-history-with-over-127-million-viewers/'
}
```

## Data Extracted

### Metrics
The skill automatically extracts the following metrics from article text:
- **Viewer counts**: Total viewers (in millions)
- **Household rating**: Nielsen's standard TV rating metric
- **Household share**: Percentage of households watching TV tuned to the program
- **Peak audience**: Maximum viewership during broadcast
- **Year-over-year change**: Percentage change from previous year
- **Broadcast time**: Start and end times

### Super Bowl Historical Table
When present, extracts structured data including:
- Super Bowl number (I through LIX)
- Broadcasting network(s)
- Total viewers (P2+)
- Household rating
- Broadcast date

The historical table spans from Super Bowl I (1967) to present, with 60+ entries.

## Response Format

All responses include:
- `success`: Boolean indicating if the operation succeeded
- `error`: Error message if unsuccessful
- Data specific to the function called

### Success Response Example
```json
{
  "success": true,
  "article": {
    "headline": "Super Bowl LIX Makes TV History With Over 127 Million Viewers",
    "date_published": "2025-02-11T21:00:49Z",
    "url": "https://www.nielsen.com/news-center/2025/...",
    "content": "Full article text...",
    "metrics": {
      "viewer_mentions_millions": [127.7, 137.7],
      "household_rating": 41.7,
      "household_share": 83,
      "peak_audience_millions": 137.7
    },
    "super_bowl_data": [
      {
        "super_bowl": "LIX",
        "network": "FOX, Tubi, Telemundo, FOX Deportes",
        "viewers": "127,713,000",
        "rating": "41.7",
        "date": "Feb. 9, 2025"
      }
      // ... more entries
    ]
  }
}
```

## Use Cases

1. **Historical Research**: Access decades of Super Bowl viewership trends
2. **TV Measurement**: Extract Nielsen's official ratings data for analysis
3. **Content Discovery**: Search for articles on specific topics
4. **Data Analysis**: Convert structured tables for statistical analysis
5. **Media Monitoring**: Track viewership metrics for major broadcasts

## Technical Details

- Uses HTTP requests (aiohttp) for fast data retrieval
- Parses HTML with BeautifulSoup for reliable extraction
- RSS feed access for article discovery
- JSON-LD structured data parsing for metadata
- No browser automation required (pure HTTP)
- Handles both modern and legacy article formats

## Limitations

- Only works with Nielsen News Center URLs (www.nielsen.com/news-center/*)
- Some articles may not contain structured data tables
- RSS feed only shows recent 10 articles by default
- Data extraction depends on consistent HTML structure