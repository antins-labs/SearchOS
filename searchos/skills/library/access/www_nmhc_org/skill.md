# NMHC Top 50 Lists Access Skill

Extract apartment industry rankings from the National Multifamily Housing Council (NMHC) Top 50 lists.

## Overview

The NMHC Top 50 is an annual ranking of the largest apartment industry companies in the United States. This skill provides programmatic access to:

- **Top Managers**: Companies ranked by units under management
- **Top Owners**: Companies ranked by units owned
- **Top Builders**: Companies ranked by units started/construction

## Available Data

### Years
- 2020 through 2025 data is available
- New lists typically published in Q1 of each year

### List Sizes
- **Managers**: 50 companies
- **Owners**: 50 companies  
- **Builders**: 25-50 companies (varies by year)

### Data Fields
Each ranking entry includes:
| Field | Description |
|-------|-------------|
| `rank` | Current year ranking position (1-50) |
| `rank_previous_year` | Previous year rank (null if new to list) |
| `company` | Company name |
| `units` | Unit count (managed, owned, or started) |
| `units_previous_year` | Previous year unit count |
| `ceo` | Chief Executive Officer name |
| `hq_city` | Headquarters city |
| `hq_state` | Headquarters state (2-letter code) |

## Functions

### `get_rankings`

Retrieve a complete ranking list for a specific category and year.

**Parameters:**
- `list_type` (string, default: "managers"): One of "managers", "owners", "builders"
- `year` (integer, default: 2025): Year of rankings (2020-2025)
- `limit` (integer, optional): Maximum number of results

**Example:**
```python
result = await execute({
    "function": "get_rankings",
    "list_type": "managers",
    "year": 2025,
    "limit": 10
})
```

**Response:**
```json
{
  "list_type": "managers",
  "year": 2025,
  "total_count": 10,
  "url": "https://www.nmhc.org/research-insight/the-nmhc-50/top-50-lists/2025-top-managers-list/",
  "rankings": [
    {
      "rank": 1,
      "rank_previous_year": 1,
      "company": "Greystar",
      "units": 946742,
      "units_previous_year": 814313,
      "ceo": "Bob Faith",
      "hq_city": "Charleston",
      "hq_state": "SC"
    },
    ...
  ],
  "status": "success"
}
```

### `search_companies`

Search for companies by name across one or all list types.

**Parameters:**
- `query` (string, required): Company name search (case-insensitive substring match)
- `list_type` (string, optional): Specific list to search, or omit for all lists
- `year` (integer, default: 2025): Year of rankings

**Example:**
```python
result = await execute({
    "function": "search_companies",
    "query": "Greystar"
})
```

### `get_company_details`

Get rankings for a specific company across all list types (managers, owners, builders).

**Parameters:**
- `company_name` (string, required): Exact or partial company name
- `year` (integer, default: 2025): Year of rankings

**Example:**
```python
result = await execute({
    "function": "get_company_details",
    "company_name": "MAA"
})
```

**Response:**
```json
{
  "company": "MAA",
  "year": 2025,
  "found": true,
  "rankings": [
    {
      "list_type": "managers",
      "rank": 12,
      "company": "MAA",
      "units": 102348,
      "ceo": "H. Eric Bolton, Jr.",
      "hq_city": "Germantown",
      "hq_state": "TN"
    },
    {
      "list_type": "owners",
      "rank": 2,
      "company": "MAA",
      "units": 102348,
      "ceo": "H. Eric Bolton, Jr.",
      "hq_city": "Germantown",
      "hq_state": "TN"
    }
  ],
  "status": "success"
}
```

### `get_list_info`

Get metadata about available lists and years.

**Example:**
```python
result = await execute({
    "function": "get_list_info"
})
```

## Use Cases

### Market Research
- Identify largest players in multifamily real estate
- Analyze market share trends year-over-year
- Compare manager vs. owner portfolios

### Competitive Analysis
- Track competitor rankings and growth
- Identify new market entrants
- Monitor CEO changes

### Investment Research
- Find largest apartment owners by portfolio size
- Compare builder activity trends
- Identify potential acquisition targets

### Industry Analysis
- Track consolidation trends (rankings changes)
- Analyze geographic distribution of HQ locations
- Measure industry wide growth (total units)

## Source

- **Publisher**: National Multifamily Housing Council (NMHC)
- **URL**: https://www.nmhc.org/research-insight/the-nmhc-50/
- **Data Format**: Server-side rendered HTML tables
- **Update Frequency**: Annual (typically Q1)

## Technical Notes

- Data is extracted from HTML tables using BeautifulSoup
- No authentication or session cookies required
- Stock photos and some company logos available through details panels
- Historical data (unit counts, rankings) may show trends over time
- Company names may include footnotes (* symbols) for special designations

## Limitations

- Only current year data is published on each list page
- Historical trends require comparing separate year lists
- Some companies may appear in multiple categories with different rankings
- Unit counts may include properties under development for builders