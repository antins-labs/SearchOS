# U.S. Government Shutdowns Data

This skill provides access to historical data about U.S. federal government shutdowns
from the House History website (history.house.gov).

## Data Source

Due to bot protection (Akamai) on the live history.house.gov website, this skill
retrieves data from the Internet Archive's Wayback Machine, which hosts archived
snapshots of the official page.

**Official source:** https://history.house.gov/Institution/Shutdown/Government-Shutdowns/

## Available Functions

### list

List all government shutdowns with optional filtering.

**Parameters:**
- `fiscal_year` (optional): Filter by fiscal year (e.g., "1996", "2019")
- `min_duration` (optional): Minimum duration in days
- `max_duration` (optional): Maximum duration in days  
- `procedures_followed` (optional): Filter by whether shutdown procedures were followed (true/false)

**Example:**
```json
{
  "function": "list",
  "min_duration": 10
}
```

### stats

Get summary statistics about all government shutdowns.

**Returns:**
- Total number of shutdowns
- Total days of shutdowns
- Average, maximum, and minimum durations
- Shutdowns by fiscal year
- Count of procedures followed vs not followed

**Example:**
```json
{
  "function": "stats"
}
```

### search

Search shutdown records by keyword across all text fields.

**Parameters:**
- `query` (required): Search term

**Example:**
```json
{
  "function": "search",
  "query": "2019"
}
```

### longest

Get the longest government shutdowns, sorted by duration.

**Parameters:**
- `limit` (optional): Number of results to return (default: 5)

**Example:**
```json
{
  "function": "longest",
  "limit": 3
}
```

## Data Fields

Each shutdown record contains:

- **Fiscal Year**: The fiscal year in which the shutdown occurred
- **Date Funding Ended**: The date government funding expired
- **Duration of Funding Gap (in Days)**: Length of the shutdown
- **Date Funding Restored**: The date government operations resumed
- **Shutdown Procedures Followed**: Whether formal shutdown procedures were implemented
- **Legislation Restoring Funding**: The bill or resolution that ended the shutdown

## Notable Shutdowns

The data includes 20 funding gaps from fiscal years 1977-2019, with the longest
being the 34-day shutdown from December 2018 to January 2019.

## Footnotes

The original source includes detailed footnotes citing Congressional Research
Service reports, newspaper articles, and legal references that provide additional
context for each shutdown.

## Notes

- Data is retrieved from archived snapshots to bypass bot protection
- The count of 39 mentions in the notes refers to total attempts with failed
  extractions; this skill successfully parses all 20 shutdown records
- All dates are in U.S. format (Month Day, Year)