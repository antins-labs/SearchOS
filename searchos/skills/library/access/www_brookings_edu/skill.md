# Brookings Trump Administration Turnover Tracker

This skill extracts structured data from the Brookings Institution's tracking of turnover in the Trump administration, providing access to cabinet departures, senior staff ("A Team") turnover, and cross-administration comparisons.

## Data Sources

The Brookings article "Tracking turnover in the Trump administration" by Kathryn Dunn Tenpas contains:

1. **Embedded Datawrapper Charts** - CSV data comparing turnover across administrations (Reagan through Trump)
2. **HTML Tables** - Detailed records of individual departures with position, name, prior job, nature of departure, date, destination, and successor

## Available Functions

### get_article_info

Returns article metadata including title, author, publication date, last modified date, and summary notes.

**Example:**
```python
result = await execute({'function': 'get_article_info'})
```

### get_cabinet_turnover_comparison

Returns cabinet-level departure counts by year for Reagan, H.W. Bush, Clinton, W. Bush, Obama, and Trump administrations.

**Example:**
```python
result = await execute({'function': 'get_cabinet_turnover_comparison'})
# Returns: List of dicts with President, Year 1-4, and Total columns
```

### get_ateam_turnover_comparison

Returns A Team (senior White House staff) departure counts by year across administrations.

**Example:**
```python
result = await execute({'function': 'get_ateam_turnover_comparison'})
# Returns: Comparison data with N values and turnover by year
```

### get_ateam_departures

Returns detailed records of Trump administration A Team departures including position, name, prior job, nature of departure, date, destination, and successor.

**Parameters:**
- `year` (optional): Filter to specific year (1, 2, 3, or 4)

**Example:**
```python
# Get all A Team departures
result = await execute({'function': 'get_ateam_departures'})

# Get Year 1 departures only
result = await execute({'function': 'get_ateam_departures', 'year': 1})
```

### get_serial_turnover

Returns positions that underwent multiple turnovers, showing the original appointee and all replacements.

**Example:**
```python
result = await execute({'function': 'get_serial_turnover'})
# Shows positions like Chief of Staff (6 occupants), White House Communications Director (6 occupants), etc.
```

### get_cabinet_departures

Returns detailed records of Trump cabinet member departures.

**Example:**
```python
result = await execute({'function': 'get_cabinet_departures'})
```

### get_all_data

Returns all available data in a single comprehensive response.

**Example:**
```python
result = await execute({'function': 'get_all_data'})
```

## Data Structure

### A Team Departure Record
```
{
  "Year": "1",
  "Position": "National Security Advisor (ST)",
  "Name": "Michael Flynn",
  "Prior job": "Trump Campaign",
  "Nature of departure*": "RUP",
  "Date of departure announcement": "2/13/2017",
  "Where to?": "Unknown",
  "Successor": "H.R. McMaster"
}
```

### Turnover Comparison Record
```
{
  "President": "Trump (N=65)",
  "Year 1": "35",
  "Year 2": "31",
  "Year 3": "17",
  "Year 4": "9",
  "Total turnover": "92"
}
```

### Cabinet Departure Record
```
{
  "Year": "1",
  "Position": "Secretary of Homeland Security",
  "Name": "John F. Kelly",
  "Prior job": "U.S. Marine Corps",
  "Nature of departure": "Promoted",
  "Date of departure announcement": "7/28/2017",
  "Where to?": "White House Chief of Staff",
  "Successor": "Kirstjen Nielsen*"
}
```

## Key Findings (from the article)

- **92%** of Trump A Team positions (60/65) turned over during his term
- **45%** of A Team departures underwent serial turnover (turned over 2+ times)
- Trump had **14** cabinet departures, the highest among recent administrations
- Trump had **92** A Team departures, significantly higher than predecessors

## Notes

- "ST" in position names indicates positions that underwent Serial Turnover
- "RUP" in departure nature means "Resigned Under Pressure"
- Data is sourced from multiple news websites, LinkedIn, WhiteHouse.gov, and other government websites
- The article tracks "A Team" positions defined as senior advisors, counselors, and directors who typically have the "Assistant to the President" (AP) designation

## Error Handling

All functions return a dict with:
- `success`: boolean indicating if the request succeeded
- `data`: the requested data (on success)
- `error`: error message string (on failure)
- `error_type`: exception class name (on failure)