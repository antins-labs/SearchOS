# Olympedia Database Access Skill

This skill provides structured access to [Olympedia.org](https://www.olympedia.org), the definitive database for Olympic athlete records and competition results.

## Overview

Olympedia is a comprehensive database containing detailed information about:

- **Athletes**: Biographical data, Olympic participation history, medal records
- **Events**: Competition results, round-by-round data, podium finishers
- **Countries**: National Olympic Committee participation records
- **Games**: Olympic editions, venues, dates, and statistics

## Functions

### `get_athlete`

Retrieve a comprehensive athlete profile by Olympedia ID.

**Parameters:**
- `athlete_id` (required): Olympedia athlete ID (e.g., "93860")

**Returns:**
- Athlete name and ID
- Biographical information (birth date, measurements, affiliations)
- National Olympic Committee (NOC)
- Olympic results with events, positions, and medals
- Medal summary (if available)

**Example:**
```python
result = await execute({
    "function": "get_athlete",
    "athlete_id": "93860"  # Michael Phelps
})
```

**Sample Output:**
```json
{
  "id": "93860",
  "url": "https://www.olympedia.org/athletes/93860",
  "name": "Michael Phelps",
  "sex": "Male",
  "full_name": "Michael Fred Phelps, II",
  "born": "30 June 1985 in Baltimore, Maryland (USA)",
  "measurements": "193 cm / 91 kg",
  "noc": "United States",
  "olympic_results": [
    {
      "games": "2004 Summer Olympics",
      "discipline_(sport)_/_event": "100 metres Butterfly, Men",
      "pos": "1",
      "medal": "Gold"
    }
  ]
}
```

### `get_results`

Retrieve detailed competition results for an Olympic event.

**Parameters:**
- `event_id` (required): Olympedia event ID (e.g., "8466")

**Returns:**
- Event name and details (date, location, status)
- Participant count and country breakdown
- Complete results with positions and times
- Podium finishers (gold, silver, bronze)
- Round-by-round data (heats, semi-finals, finals)

**Example:**
```python
result = await execute({
    "function": "get_results",
    "event_id": "8466"  # 200m Butterfly Men, Sydney 2000
})
```

**Sample Output:**
```json
{
  "id": "8466",
  "event_name": "200 metres Butterfly, Men",
  "date": "18 – 19 September 2000",
  "status": "Olympic",
  "location": "Sydney International Aquatic Centre",
  "participants": "46 from 40 countries",
  "podium": [
    {"position": 1, "medal": "Gold", "name": "Tom Malchow", "country": "USA"},
    {"position": 2, "medal": "Silver", "name": "Denys Sylantiev", "country": "UKR"},
    {"position": 3, "medal": "Bronze", "name": "Justin Norris", "country": "AUS"}
  ],
  "results": [
    {"pos": "1", "competitor": "Tom Malchow", "noc": "USA", "final": "1:55.35 (1)"}
  ]
}
```

### `search_athletes`

Search for athletes by name.

**Parameters:**
- `query` (required): Search query (name or partial name)

**Returns:**
- List of matching athletes with IDs and names
- Count of matches found

**Example:**
```python
result = await execute({
    "function": "search_athletes",
    "query": "Bolt"
})
```

**Sample Output:**
```json
{
  "query": "Bolt",
  "count": 5,
  "athletes": [
    {"id": "104133", "name": "Usain Bolt", "url": "https://www.olympedia.org/athletes/104133"},
    {"id": "87562", "name": "Michelle Bolt", "url": "https://www.olympedia.org/athletes/87562"}
  ]
}
```

## Finding IDs

### Athlete IDs
Found in Olympedia athlete URLs:
- URL: `https://www.olympedia.org/athletes/93860`
- ID: `"93860"`

Use `search_athletes` to find athlete IDs by name.

### Event IDs
Found in Olympedia results URLs:
- URL: `https://www.olympedia.org/results/8466`
- ID: `"8466"`

Event IDs can be found in athlete results (the `discipline_(sport)_/_event_link` field contains the event ID).

## Data Coverage

The database covers:
- **All Olympic Games** from Athens 1896 to present
- **Summer and Winter Olympics**
- **Athletes**: Competitors, coaches, officials, flag bearers
- **Sports**: All Olympic sports with detailed event results
- **Countries**: All participating NOCs

## Error Handling

The skill returns structured error objects:

```json
{
  "error": "Athlete page not found or invalid structure",
  "error_code": "NOT_FOUND"
}
```

Common error codes:
- `MISSING_PARAM`: Required parameter not provided
- `NOT_FOUND`: Requested resource not found
- `FETCH_ERROR`: Failed to fetch page
- `TIMEOUT`: Request timed out
- `CSRF_ERROR`: Failed to obtain search token

## Rate Limits

Please respect the site's resources:
- Recommended: 2 requests per second
- Maximum: 100 requests per minute

## Technical Details

- **Access Method**: Direct HTTP requests with HTML parsing
- **No Authentication Required**: Site is publicly accessible
- **Data Format**: Structured JSON extracted from HTML tables
- **Library Used**: BeautifulSoup for HTML parsing, aiohttp for async HTTP

## Use Cases

1. **Athlete Research**: Get comprehensive profiles with career statistics
2. **Historical Analysis**: Access competition results from any Olympic Games
3. **Medal Tracking**: Track athlete medals and podium finishes
4. **Event Discovery**: Find event IDs from athlete result links
5. **Name Search**: Locate athletes by partial name matching