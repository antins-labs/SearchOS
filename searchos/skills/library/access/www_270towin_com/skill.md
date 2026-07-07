# 270toWin Historical Election Data Access Skill

Access comprehensive U.S. presidential election data from 270toWin.com.

## Overview

This skill provides structured access to historical U.S. presidential election results from 1789 to the present. It retrieves election data including:

- **Election results**: Winners, losers, and vote counts
- **Electoral votes**: State-by-state electoral college results
- **Popular votes**: National popular vote totals (available for elections after 1824)
- **Candidate information**: Names, parties, and vote breakdowns
- **Historical context**: Election facts and notable events

## Available Functions

### `get_election`

Get detailed results for a specific presidential election year.

**Parameters:**
- `year` (integer, required): Election year (1789-2024, every 4 years)

**Returns:**
```json
{
  "year": 1824,
  "title": "1824 Presidential Election",
  "winner": {
    "name": "John Quincy Adams",
    "party": "Democratic-Republican",
    "electoral_votes": 84,
    "popular_votes": 108740
  },
  "candidates": [
    {
      "Candidate": "Andrew Jackson",
      "Party": "Democratic-Republican",
      "Electoral Votes": "99",
      "Popular Votes": "153,544",
      "electoral_votes": 99,
      "popular_votes": 153544,
      "winner": false
    },
    {
      "Candidate": "John Quincy Adams",
      "Party": "Democratic-Republican",
      "Electoral Votes": "84",
      "Popular Votes": "108,740",
      "electoral_votes": 84,
      "popular_votes": 108740,
      "winner": true
    }
  ],
  "facts": {
    "description": "Results of the presidential election of 1824...",
    "notes": ["This election is notable for being the only time..."]
  }
}
```

**Examples:**
```python
# Get 1796 election (first contested election)
result = await execute({'function': 'get_election', 'year': 1796})

# Get 2020 election results
result = await execute({'function': 'get_election', 'year': 2020})

# Get 1860 election (Lincoln's first victory)
result = await execute({'function': 'get_election', 'year': 1860})
```

### `list_elections`

Get a complete list of all historical presidential elections.

**Parameters:** None

**Returns:**
```json
{
  "total_elections": 60,
  "first_year": 1789,
  "last_year": 2024,
  "elections": [
    {"year": 1789, "text": "1789", "url": "https://www.270towin.com/1789-election/"},
    {"year": 1792, "text": "1792", "url": "https://www.270towin.com/1792-election/"},
    {"year": 1796, "text": "1796", "url": "https://www.270towin.com/1796-election/"}
    // ... all elections through 2024
  ]
}
```

### `search_elections`

Search for elections by winner name or party affiliation.

**Parameters:**
- `query` (string, required): President name or party name

**Returns:**
```json
{
  "query": "lincoln",
  "normalized_query": "abraham lincoln",
  "total_matches": 2,
  "matches": [
    {
      "year": 1860,
      "winner": "Abraham Lincoln",
      "party": "Republican",
      "electoral_votes": 180,
      "url": "https://www.270towin.com/1860-election/"
    },
    {
      "year": 1864,
      "winner": "Abraham Lincoln",
      "party": "Republican/National Union",
      "electoral_votes": 212,
      "url": "https://www.270towin.com/1864-election/"
    }
  ]
}
```

**Supported name shortcuts:**
- Common aliases: "jfk" → John F. Kennedy, "fdr" → Franklin D. Roosevelt, "lbj" → Lyndon B. Johnson
- Partial names: "roosevelt" → Theodore Roosevelt / Franklin D. Roosevelt
- Party names: "republican", "democratic", "federalist", etc.

**Examples:**
```python
# Search by president name
result = await execute({'function': 'search_elections', 'query': 'lincoln'})

# Search by party
result = await execute({'function': 'search_elections', 'query': 'federalist'})

# Search with nickname
result = await execute({'function': 'search_elections', 'query': 'jfk'})
```

## Data Coverage

### Year Range
- **First election**: 1789 (George Washington, unopposed)
- **Latest election**: 2024
- **Total elections**: 60+

### Data Availability

| Period | Electoral Votes | Popular Votes | Notes |
|--------|-----------------|---------------|-------|
| 1789-1824 | ✓ | ✗ | Popular vote not consistently recorded |
| 1828-present | ✓ | ✓ | Full popular vote data available |

### Special Elections
- **1789, 1792**: Washington essentially unopposed
- **1824**: Decided by House of Representatives (Jackson won popular/electoral but lost)
- **1876**: Contested election, Hayes won by one electoral vote
- **2000**: Bush v. Gore, decided by Supreme Court

## Historical Notes

### Party Evolution
- **Federalist** (1789-1816): Adams, Pinckney
- **Democratic-Republican** (1796-1824): Jefferson, Madison, Monroe, J.Q. Adams
- **Democratic** (1828-present): Jackson through Biden
- **Whig** (1836-1852): Harrison, Tyler, Taylor, Fillmore
- **Republican** (1856-present): Lincoln through Trump

### Notable Elections
- **1800**: First peaceful transfer of power between parties
- **1860**: Lincoln elected, Southern states secede
- **1912**: Wilson wins with 3-way split (Taft, Roosevelt, Wilson)
- **1932**: FDR begins 4-term tenure
- **1960**: Kennedy wins by narrow margin
- **2000**: Bush wins despite losing popular vote

## Error Handling

The skill returns structured error messages for common issues:

```json
{
  "error": "Not a presidential election year",
  "error_type": "validation",
  "message": "1999 was not a presidential election year. Presidential elections are held every 4 years from 1788 (1789, 1792, 1796, ...)"
}
```

**Common errors:**
- Invalid year (not a number or out of range)
- Not a presidential election year (e.g., 2019)
- Missing required parameters
- Network/fetch errors

## Rate Limits

The skill uses conservative rate limiting:
- **2 requests per second**
- **30 requests per minute**

Historical data is cached for 1 hour since it doesn't change.

## Use Cases

### Educational
- Teach U.S. electoral history
- Study party evolution
- Analyze voting patterns over time

### Research
- Compare electoral margins across elections
- Study third-party performance
- Track battleground state changes

### Data Visualization
- Create electoral vote timelines
- Map voting patterns by region
- Compare historical campaigns

## Source

Data retrieved from [270toWin](https://www.270towin.com), a comprehensive resource for:
- Historical U.S. presidential election results
- Electoral college maps and projections
- Senate, House, and Governor race data
- Polling and predictions

## Implementation Notes

- Uses HTTP requests (httpx) for efficient data retrieval
- HTML parsing with BeautifulSoup
- No JavaScript required (static HTML content)
- Supports both synchronous and async execution
- Automatic winner detection from table data