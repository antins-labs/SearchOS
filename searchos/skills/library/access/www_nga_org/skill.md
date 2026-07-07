# NGA Former Governors Access Skill

This skill fetches historical governor data from the National Governors Association (NGA) website at www.nga.org. It provides comprehensive information about former governors of all 50 U.S. states and territories.

## Features

- **List States**: Get a complete list of all available U.S. states and territories with NGA governor data
- **Get Governors**: Retrieve all former governors for a specific state with full details
- **Search Governors**: Search across states by governor name, political party, or filter by state

## Data Retrieved

For each governor, the skill extracts:
- **Name**: Full name with title (e.g., "Gov. Roy Cooper")
- **State**: State or territory name
- **Terms**: Structured term data including start/end years for each term (handles non-consecutive terms)
- **Party**: Political party affiliation
- **Link**: URL to the governor's NGA profile page

## Usage Examples

### List all available states

```python
result = await execute({'function': 'list_states'})
# Returns list of 56 states/territories with slugs and URLs
```

### Get governors for a specific state

```python
result = await execute({
    'function': 'get_governors',
    'state': 'North Carolina'  # or 'north-carolina'
})
# Returns all 69 governors from North Carolina
```

### Search governors by name

```python
result = await execute({
    'function': 'search_governors',
    'query': 'bush'
})
# Returns governors with "bush" in their name
```

### Filter by party and state

```python
result = await execute({
    'function': 'search_governors',
    'party': 'Democratic',
    'state_filter': 'california',
    'limit': 10
})
# Returns up to 10 Democratic governors from California
```

## Data Source

All data is scraped from the public NGA website:
- Base URL: `https://www.nga.org/former-governors/{state-slug}/`
- No authentication required
- Data is served as static HTML tables

## Response Format

All responses include:
- `success`: Boolean indicating if the operation succeeded
- `function`: The function that was executed
- `error`: Error message (if success is false)
- Function-specific data fields

### get_governors response

```json
{
  "success": true,
  "function": "get_governors",
  "state": "North Carolina",
  "slug": "north-carolina",
  "url": "https://www.nga.org/former-governors/north-carolina/",
  "total_governors": 69,
  "governors": [
    {
      "name": "Gov. Roy Cooper",
      "state": "North Carolina",
      "terms": [
        {"start": "2021", "end": "2025", "raw": "2021 - 2025"},
        {"start": "2017", "end": "2020", "raw": "2017 - 2020"}
      ],
      "party": "Democratic",
      "link": "https://www.nga.org/governor/roy-cooper/"
    },
    // ... more governors
  ]
}
```

## Notes

- Governor terms are carefully parsed to handle non-consecutive terms (e.g., governors who served multiple separate terms)
- Party affiliations may include multiple parties (e.g., "Democratic (1st); Independent (2nd)")
- Historical data may have incomplete party affiliations for very early governors
- The skill uses async HTTP requests for efficient parallel searching across multiple states