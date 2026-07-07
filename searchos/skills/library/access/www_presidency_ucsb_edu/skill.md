# UCSB Presidency Project Election Statistics Access Skill

## Overview

This skill extracts structured US presidential election data from The American Presidency Project at [presidency.ucsb.edu](https://www.presidency.ucsb.edu/statistics/elections/).

## Data Extracted

### Candidate Information
- Presidential and vice presidential candidates for each major party
- Political party affiliation
- Electoral votes received
- Electoral vote percentage
- Popular votes received
- Popular vote percentage
- Winner indicator

### State-by-State Results
For each state (including District of Columbia):
- Total votes cast
- Votes for each party's candidate
- Vote percentage for each candidate
- Electoral votes won (shown for the winning candidate)

## Functions

### `get_election`

Get complete election data for a specific year.

**Parameters:**
- `year` (integer, required): Presidential election year (e.g., 2000, 2004, 2008)

**Example:**
```python
result = await execute({
    "function": "get_election",
    "year": 2000
})
```

**Sample Response:**
```json
{
  "year": 2000,
  "candidates": [
    {
      "party": "Republican",
      "presidential_candidate": "George W. Bush",
      "vice_presidential_candidate": "Richard Cheney",
      "electoral_votes": 271,
      "electoral_vote_percentage": "50.4%",
      "popular_votes": "50,455,156",
      "popular_vote_percentage": "47.9%",
      "winner": true
    },
    {
      "party": "Democratic",
      "presidential_candidate": "Albert Gore, Jr.",
      "vice_presidential_candidate": "Joseph Lieberman",
      "electoral_votes": 266,
      "electoral_vote_percentage": "49.4%",
      "popular_votes": "50,992,335",
      "popular_vote_percentage": "48.4%",
      "winner": false
    }
  ],
  "state_results": [
    {
      "state": "Florida",
      "total_votes": "5,963,110",
      "republican_votes": "2,912,790",
      "republican_percentage": "48.8",
      "republican_electoral_votes": "25",
      "democratic_votes": "2,912,253",
      "democratic_percentage": "48.8"
    }
  ],
  "total_states": 51,
  "parties": ["Republican", "Democratic"]
}
```

### `get_state_results`

Get election results for a specific state in a given year.

**Parameters:**
- `year` (integer, required): Presidential election year
- `state` (string, required): State name (case-insensitive)

**Example:**
```python
result = await execute({
    "function": "get_state_results",
    "year": 2008,
    "state": "California"
})
```

### `list_elections`

List information about available election years.

**Example:**
```python
result = await execute({
    "function": "list_elections"
})
```

## Technical Details

### Implementation

- Uses direct HTTP requests with `httpx` for efficient data retrieval
- Parses HTML using `BeautifulSoup` for structured extraction
- No browser automation required

### Data Validation

- Validates election year is a valid presidential election year (every 4 years from 1789)
- Returns structured error messages for invalid years or missing data
- Handles both standard and edge case page formats

### Notable Elections

- **2000**: Bush vs. Gore, includes Green party (Nader), famously close Florida results
- **2004**: Bush vs. Kerry
- **2008**: Obama vs. McCain, Democrats listed first (won election)

## Error Handling

Returns structured error objects for:
- Missing required parameters
- Invalid election years
- HTTP errors or timeouts
- Missing or malformed data

**Example Error:**
```json
{
  "error": "State 'Flordia' not found in 2000 election results",
  "year": 2000,
  "available_states": ["Alabama", "Alaska", "Arizona", "..."],
  "total_available": 51
}
```

## Source

Data sourced from The American Presidency Project, University of California, Santa Barbara.
URL: https://www.presidency.ucsb.edu/statistics/elections/{year}