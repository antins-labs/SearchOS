# Statista Access Skill

Access statistics, data tables, and metadata from Statista (www.statista.com).

## Features

- **Get Statistic**: Extract complete data from individual Statista statistic pages
  - Title and description
  - Full data tables with headers
  - Metadata (release date, region, time period, etc.)
  - Statistic ID and URL

- **Search**: Find statistics matching your query
  - Returns list of matching statistics with IDs, titles, and URLs
  - Use the results to fetch detailed data with `get_statistic`

## Usage

### Get a Statistic by ID or URL

```python
# By ID
result = await execute({
    'function': 'get_statistic',
    'url_or_id': '1058725'
})

# By URL
result = await execute({
    'function': 'get_statistic',
    'url_or_id': 'https://www.statista.com/statistics/1058725/olympic-medals-ranking-latin-american-countries/'
})
```

### Search for Statistics

```python
result = await execute({
    'function': 'search',
    'query': 'olympic medals',
    'max_results': 10
})
```

## Return Values

### get_statistic

Returns a dictionary with:

- `success`: Boolean indicating if the request was successful
- `url`: The URL used
- `title`: Statistic title
- `description`: Description text
- `statistic_id`: Statista's ID for this statistic
- `table`: Dictionary with `headers`, `data` (list of rows), and `row_count`
- `metadata`: Dictionary of additional info (Release date, Region, etc.)
- `error`: Error message if unsuccessful

### search

Returns a dictionary with:

- `success`: Boolean indicating if the request was successful
- `query`: The search query used
- `results`: List of dictionaries with `id`, `title`, and `url`
- `count`: Number of results returned
- `error`: Error message if unsuccessful

## Notes

- All data is extracted from public Statista pages
- Some advanced features (full source information, downloads) require a Statista account
- Data tables are extracted from HTML - complex chart visualizations may not be fully represented
- The skill works without authentication for publicly viewable statistics

## Example Output

```json
{
  "success": true,
  "url": "https://www.statista.com/statistics/1058725/olympic-medals-ranking-latin-american-countries/",
  "title": "Summer Olympic medals ranking in Latin America & the Caribbean 1896-2024, by country",
  "description": "Cuba holds the record...",
  "statistic_id": "1058725",
  "table": {
    "headers": ["Characteristic", "Gold", "Silver", "Bronze"],
    "data": [
      ["Cuba", "86", "70", "88"],
      ["Brazil", "40", "49", "81"],
      ...
    ],
    "row_count": 29
  },
  "metadata": {
    "Release date": "August 2024",
    "Region": "Latin America and the Caribbean",
    "Survey time period": "including medals won in Paris 2024"
  }
}
```