# National Archives Electoral College Access Skill

## Overview

This skill provides structured access to U.S. Electoral College results from the National Archives (archives.gov). It extracts and normalizes election data from official government records for all presidential elections from 1789 to the present.

## Available Functions

### `get_results`

Fetch comprehensive electoral college results for a specific election year.

**Parameters:**
- `year` (required): Four-digit election year as a string (e.g., "2020", "1789")

**Returns:**
```json
{
  "year": "2020",
  "title": "2020 Electoral College Results",
  "url": "https://www.archives.gov/electoral-college/2020",
  "summary": {
    "president": {
      "name": "Joseph R. Biden Jr.",
      "party": "D"
    },
    "main_opponent": {
      "name": "Donald J. Trump",
      "party": "R"
    },
    "electoral_votes": {
      "winner": 306,
      "main_opponent": 232,
      "total": 538,
      "majority_needed": 270
    },
    "vice_president": {
      "name": "Kamala D. Harris",
      "party": "D"
    },
    "vp_opponent": {
      "name": "Michael R. Pence",
      "party": "R"
    },
    "notes": "..."
  },
  "state_results": [...]
}
```

### `list_years`

List all available presidential election years in the database.

**Parameters:** None

**Returns:**
```json
{
  "years": ["1789", "1792", "1796", ..., "2020", "2024"],
  "count": 60,
  "min_year": "1789",
  "max_year": "2024"
}
```

## Data Coverage

- **Time Range:** 1789 - Present
- **Election Cycle:** Every 4 years (presidential elections)
- **Total Elections:** 60+ elections documented

## Data Structure

### Summary Table
Each election includes:
- **President**: Winner with party affiliation
- **Main Opponent**: Runner-up with party affiliation
- **Other Opponents**: Additional candidates with vote counts (if applicable)
- **Electoral Votes**: Winner, opponent, total, and majority threshold
- **Vice President**: Elected VP with party
- **VP Opponent**: Opposing VP candidate (modern elections)
- **Notes**: Historical context and special circumstances

### State-by-State Results
Format varies by era:

**Early Elections (pre-1828):**
- Candidates as rows, states as columns
- State abbreviations: CT, DE, GA, MD, MA, NH, NJ, PA, SC, VA, etc.

**Modern Elections:**
- States as rows, candidates as columns
- Includes each state's electoral vote count
- Candidate votes by state

## Historical Notes

### Early Elections (1789-1800)
- Original electoral system: Each elector cast two votes for President
- Candidate with most votes became President, second-most became Vice President
- No formal party tickets
- The 12th Amendment (1804) changed this to separate votes for President and Vice President

### Interesting Elections

1. **1789**: George Washington elected unanimously (69 electoral votes)
2. **1800**: Tie between Jefferson and Burr, decided by House of Representatives
3. **1824**: John Quincy Adams elected by House despite losing popular/electoral vote
4. **1876**: Disputed election, Hayes wins by one electoral vote
5. **2000**: Bush v. Gore, Supreme Court intervention
6. **2020**: Contested results, January 6 Capitol events

## Usage Examples

### Get 2020 Election Results
```python
result = await execute({
    "function": "get_results",
    "year": "2020"
})
# Returns Biden vs. Trump results with state-by-state breakdown
```

### Get First Presidential Election
```python
result = await execute({
    "function": "get_results",
    "year": "1789"
})
# Returns Washington's unanimous election
```

### List All Available Elections
```python
result = await execute({
    "function": "list_years"
})
# Returns list of 60+ election years from 1789 to present
```

## Error Handling

The skill returns structured error responses:

```json
{
  "error": "Invalid year format: 20",
  "note": "Year must be a four-digit number"
}
```

Common errors:
- Missing required `year` parameter
- Invalid year format (must be 4 digits)
- Year out of range (before 1789)
- Not an election year (not divisible by 4 from 1788)
- Network/timeout errors

## Data Source

All data is sourced from the official U.S. National Archives:
- **URL Pattern**: `https://www.archives.gov/electoral-college/{year}`
- **Authority**: Official U.S. government records
- **Reliability**: Primary source for electoral college data

## Rate Limiting

Recommended rate limits:
- 2 requests per second
- 30 requests per minute

The National Archives resources are public domain and freely accessible, but please use responsibly.