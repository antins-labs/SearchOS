# NPS Visitor Spending Effects (VSE) API Access Skill

## Overview

This skill provides programmatic access to the National Park Service's Visitor Spending Effects (VSE) data through the IRMA Services API. The VSE program measures the economic impact of visitor spending on local, state, and national economies.

## Data Available

### Economic Metrics
- **Jobs**: Number of jobs supported by visitor spending
- **Visitor Spending**: Total non-local visitor spending in dollars
- **Labor Income**: Wages, salaries, and employee benefits
- **Value Added**: Contribution to Gross Domestic Product (GDP)
- **Economic Output**: Total economic activity generated

### Spending Sectors (detailed view)
- Camping
- Gas
- Groceries
- Lodging
- Recreation Industries
- Restaurants
- Retail
- Transportation (local)
- Other

## Functions

### get_national_data
Get USA-wide cumulative economic impact data.

**Parameters:**
- `year` (optional, default: 2024): Year of data, 2012-2024
- `metric` (optional): Filter by specific metric

**Example:**
```json
{
  "function": "get_national_data",
  "year": 2023
}
```

### get_state_data
Get detailed economic impact data for a specific state.

**Parameters:**
- `state_code` (required): 2-letter state code (e.g., "CA", "TX", "NY")
- `year` (optional, default: 2024): Year of data, 2012-2024
- `metric` (optional): Filter by specific metric

**Example:**
```json
{
  "function": "get_state_data",
  "state_code": "CA",
  "year": 2022
}
```

### get_all_states
Get summary economic impact data for all states and territories.

**Parameters:**
- `year` (optional, default: 2024): Year of data, 2012-2024

**Example:**
```json
{
  "function": "get_all_states",
  "year": 2024
}
```

### get_park_data
Get detailed economic impact data for a specific NPS unit.

**Parameters:**
- `park_code` (required): 4-letter park code (e.g., "YELL", "YOSE", "GRCA")
- `year` (optional, default: 2024): Year of data, 2012-2024
- `metric` (optional): Filter by specific metric

**Example:**
```json
{
  "function": "get_park_data",
  "park_code": "YELL",
  "year": 2023
}
```

### get_all_parks
Get summary economic impact data for all NPS units (parks, monuments, historic sites, etc.).

**Parameters:**
- `year` (optional, default: 2024): Year of data, 2012-2024

**Example:**
```json
{
  "function": "get_all_parks",
  "year": 2023
}
```

### search_parks
Search for parks by name or code and return their economic data.

**Parameters:**
- `query` (required): Search string (matches park name or code)
- `year` (optional, default: 2024): Year of data, 2012-2024
- `limit` (optional, default: 20): Maximum number of results

**Example:**
```json
{
  "function": "search_parks",
  "query": "yellow",
  "year": 2024
}
```

### get_available_years
Get list of years for which VSE data is available.

**Example:**
```json
{
  "function": "get_available_years"
}
```

## Response Structure

### Summary Data (all_parks, all_states)
```json
{
  "query_time": "2024-01-15T12:00:00Z",
  "processing_time_ms": 150.5,
  "count": 402,
  "data": [
    {
      "park_name": "Yellowstone",
      "park_code": "YELL",
      "unit_type": "National Park",
      "latitude": 44.428,
      "longitude": -110.5885,
      "jobs": 8539.0,
      "visitor_spending": 642964000.0,
      "value_added": 776000000.0,
      "labor_income": 320000000.0,
      "economic_output": 1000000000.0,
      "analysis_year": 2024
    }
  ]
}
```

### Detailed Data (single park/state/nation)
```json
{
  "query_time": "2024-01-15T12:00:00Z",
  "processing_time_ms": 380.2,
  "data": {
    "name": "Yellowstone",
    "code": "YELL",
    "unit_type": "National Park",
    "year": 2024,
    "footnotes": [],
    "metrics_by_category": {
      "Economic Output": {
        "Camping": 23165043.0,
        "Gas": 11204785.0,
        "Groceries": 11877443.0,
        "Lodging": 237727179.0,
        "Recreation Industries": 80617588.0,
        "Restaurants": 124597294.0,
        "Retail": 33890187.0
      },
      "Jobs": {
        "Camping": 349.0,
        "Gas": 169.0,
        ...
      }
    }
  }
}
```

## Common Park Codes

| Park Name | Code |
|-----------|------|
| Yellowstone | YELL |
| Yosemite | YOSE |
| Grand Canyon | GRCA |
| Great Smoky Mountains | GRSM |
| Rocky Mountain | ROMO |
| Zion | ZION |
| Acadia | ACAD |
| Grand Teton | GRTE |
| Glacier | GLAC |
| Olympic | OLYM |

## Data Source

Data is sourced from the NPS IRMA Services API:
- Base URL: `https://irmaservices.nps.gov/vseapi`
- API Version: v4
- Documentation: `https://irmaservices.nps.gov/vseapi/swagger`

## Notes

- Data is available for years 2012-2024
- Economic values are in US dollars
- Job counts represent full-time equivalent (FTE) positions
- All data is estimated using the MGM2 economic impact model
- Park unit types include National Parks, National Monuments, National Historic Sites, National Recreation Areas, etc.

## Use Cases

- Analyze economic contribution of parks to local economies
- Compare visitor spending across parks or states
- Track economic trends over time
- Research tourism impact on gateway communities
- Support park planning and management decisions
- Calculate return on investment for park infrastructure