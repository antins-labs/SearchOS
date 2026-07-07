# University Rankings (universityrankings.ch) Access Skill

## Overview

This skill retrieves university ranking data from universityrankings.ch, a comprehensive portal that aggregates university rankings from multiple internationally recognized ranking systems. The site provides comparative ranking data from:

- **QS World University Rankings** - Published by Quacquarelli Symonds, focusing on academic reputation, employer reputation, and faculty/student ratios
- **Times Higher Education (THE) World University Rankings** - Evaluates universities on teaching, research, citations, industry income, and international outlook
- **Shanghai Ranking (ARWU)** - Academic Ranking of World Universities, focusing on research output and Nobel laureates
- **Leiden Ranking** - Bibliometric ranking focusing on scientific impact and collaboration

## Data Source

**Note:** The main universityrankings.ch website is protected by a CAPTCHA/bot detection system. This skill retrieves data via the Internet Archive's Wayback Machine, which maintains archived snapshots of the site. Data is current as of the latest available archive (typically mid-2024).

**Archive URL:** `https://web.archive.org/web/2024/http://www.universityrankings.ch`

## Functions

### 1. `get_rankings`

Get university rankings for a specific ranking system and year.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| system | string | Yes | Ranking system: "QS", "Times", "Shanghai", or "Leiden" |
| year | string | Yes | Ranking year (e.g., "2024", "2023", "2022") |
| limit | integer | No | Maximum number of results (default: 100) |

**Returns:**
```json
{
  "success": true,
  "system": "QS",
  "year": "2025",
  "total_results": 50,
  "rankings": [
    {
      "position": 1,
      "rank": "1",
      "institution": "Massachusetts Institute of Technology, MIT",
      "country": "USA",
      "trend": "=",
      "trend_description": "stable (no change from previous year)",
      "institution_id": "id6272-massachusetts_institute_of_technology_mit-usa"
    },
    ...
  ]
}
```

**Example Usage:**
```json
{
  "function": "get_rankings",
  "system": "QS",
  "year": "2025",
  "limit": 20
}
```

### 2. `get_institution`

Get detailed ranking history for a specific institution across multiple ranking systems.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| institution_id | string | Yes | Institution ID from rankings (e.g., "id6272-massachusetts_institute_of_technology_mit-usa") |

**Returns:**
```json
{
  "success": true,
  "institution_id": "id6272-massachusetts_institute_of_technology_mit-usa",
  "name": "Massachusetts Institute of Technology, MIT",
  "ranking_history": [
    {
      "year": "2024",
      "Shanghai": "3/1000",
      "QS": "1/500",
      "Times": "3/500",
      "Leiden": "..."
    },
    ...
  ],
  "available_systems": ["Shanghai", "QS", "Times", "Leiden"]
}
```

**Example Usage:**
```json
{
  "function": "get_institution",
  "institution_id": "id6272-massachusetts_institute_of_technology_mit-usa"
}
```

### 3. `search_institutions`

Search for institutions by name or filter by country within a specific ranking.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| system | string | Yes | Ranking system |
| year | string | Yes | Ranking year |
| query | string | No | Search query for institution name |
| country | string | No | Filter by country name |

**Returns:**
```json
{
  "success": true,
  "system": "QS",
  "year": "2025",
  "query": "ETH",
  "country": null,
  "total_results": 1,
  "results": [
    {
      "position": 7,
      "rank": "7",
      "institution": "Swiss Federal Institute of Technology Zurich, ETHZ",
      "country": "Switzerland",
      "trend": "=",
      "trend_description": "stable",
      "institution_id": "id6366-swiss_federal_institute_of_technology_zurich_ethz-switzerland"
    }
  ]
}
```

**Example Usage:**
```json
{
  "function": "search_institutions",
  "system": "QS",
  "year": "2025",
  "country": "Switzerland"
}
```

### 4. `list_available_years`

List available years for a ranking system.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| system | string | Yes | Ranking system |

**Returns:**
```json
{
  "success": true,
  "system": "QS",
  "years": ["2025", "2024", "2023", "2022", "2021", "2020"],
  "note": "Years based on archived data availability"
}
```

**Example Usage:**
```json
{
  "function": "list_available_years",
  "system": "Times"
}
```

## Ranking System Details

### QS World University Rankings
- Published annually by Quacquarelli Symonds
- Weightings: Academic Reputation (40%), Employer Reputation (10%), Faculty/Student Ratio (20%), Citations per Faculty (20%), International Faculty Ratio (5%), International Student Ratio (5%)
- Available years: Typically 2004-present

### Times Higher Education (THE) World University Rankings
- Published by Times Higher Education
- Weightings: Teaching (30%), Research (30%), Citations (30%), International Outlook (7.5%), Industry Income (2.5%)
- Available years: Typically 2010-present

### Shanghai Ranking (ARWU)
- Academic Ranking of World Universities by Shanghai Jiao Tong University
- Focuses on research quality, Nobel laureates, Fields medalists, and publications
- Available years: Typically 2003-present

### Leiden Ranking
- Produced by the Centre for Science and Technology Studies (CWTS) at Leiden University
- Bibliometric indicators focusing on scientific impact and collaboration
- Available years: Typically 2012-present

## Data Notes

1. **Trend Indicators:**
   - `=` : Stable position from previous year
   - Position number: Moved up (shows upward arrow)
   - `-` : Moved down position
   - `new` : New to ranking

2. **Ranking Formats:**
   - Some rankings show rank with total: "1/500" means ranked 1st out of 500 institutions
   - Ranges indicated with `-` (e.g., "51-100")

3. **Stale Data:** Due to reliance on archived snapshots, data may not reflect the most recent ranking updates. For the very latest data, visit the website directly (may require CAPTCHA completion).

## Error Handling

Functions return error objects for:
- Invalid ranking systems
- Missing required parameters
- Network/HTTP errors
- Missing data

Example error response:
```json
{
  "error": "Invalid ranking system: ABC",
  "available_systems": ["QS", "Times", "Shanghai", "Leiden"]
}
```

## Rate Limiting

The skill uses the Internet Archive's Wayback Machine, which has reasonable rate limits. Avoid making excessive requests in short periods. The default timeout is 60 seconds per request.

## License

University ranking data is compiled by universityrankings.ch (operated by Scimetrica) from various ranking publishers. This skill accesses publicly archived data for research and educational purposes.