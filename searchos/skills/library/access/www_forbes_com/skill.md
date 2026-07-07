# Forbes Billionaires List Access Skill

This skill provides structured access to Forbes World's Billionaires List data, including rankings, net worth, demographic information, and detailed profiles.

## Overview

Forbes publishes the definitive list of the world's billionaires annually, with real-time updates throughout the year based on stock prices and exchange rates. This skill exposes the underlying JSON API that powers the Forbes billionaires website, enabling programmatic access to:

- **3,400+ billionaires** ranked by net worth
- Real-time wealth valuations
- Detailed demographic data (age, country, gender)
- Industry and source of wealth categorization
- Individual profile data with bios

## API Endpoints Discovered

The skill uses the following Forbes API endpoints:

1. **List API**: `https://www.forbes.com/forbesapi/person/billionaires/{year}/position/true.json`
   - Returns paginated list of billionaires
   - Supports pagination (limit up to 500, offset for subsequent pages)
   - Provides total count for navigation

2. **Profile API**: `https://www.forbes.com/forbesapi/person/{uri}.json`
   - Returns detailed profile for a specific billionaire
   - Includes bios, quotes, and historical wealth data

3. **Directory API**: `https://bacon.forbes.com/bacon-forbes-prd/billionaires-{year}-directory/payload.json`
   - Returns metadata and articles related to the list

## Functions

### `list` - Get Billionaires List

Retrieves a paginated list of billionaires.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| limit | integer | 100 | Results per page (max 500) |
| offset | integer | 0 | Starting position for pagination |
| year | integer | 2026 | Year of the billionaires list |
| industry | string | none | Filter by industry |
| country | string | none | Filter by country of citizenship |
| gender | string | none | Filter by gender ("M" or "F") |

**Example:**
```json
{
  "function": "list",
  "limit": 50,
  "offset": 0,
  "industry": "Technology",
  "country": "United States"
}
```

**Response Structure:**
```json
{
  "billionaires": [
    {
      "uri": "elon-musk",
      "rank": 1,
      "personName": "Elon Musk",
      "finalWorth": 839000,
      "age": 54,
      "countryOfCitizenship": "United States",
      "source": "Tesla, SpaceX",
      "industries": ["Technology"],
      "gender": "M",
      "organization": "Tesla"
    }
  ],
  "total": 3428,
  "offset": 0,
  "limit": 50,
  "has_more": true
}
```

### `profile` - Get Billionaire Profile

Retrieves detailed information for a specific billionaire.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| uri | string | yes | Billionaire's URI slug (e.g., "elon-musk") |
| year | integer | no | Year of data (default 2026) |

**Example:**
```json
{
  "function": "profile",
  "uri": "elon-musk"
}
```

**Response includes:**
- Basic info (name, age, country, organization)
- Wealth data (net worth, rank, category)
- Biography snippets
- Image URLs
- Profile page URL

### `search` - Search by Name

Finds billionaires matching a name query.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| query | string | yes | Search query (partial name) |
| limit | integer | no | Max results (default 50) |
| year | integer | no | Year of list (default 2026) |

**Example:**
```json
{
  "function": "search",
  "query": "Musk"
}
```

### `top` - Get Top Billionaires

Returns the top N billionaires by net worth.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| count | integer | 10 | Number to return |
| year | integer | 2026 | Year of list |

**Example:**
```json
{
  "function": "top",
  "count": 10
}
```

### `stats` - Get Statistics

Returns summary statistics about the billionaires list.

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| year | integer | 2026 | Year of list |

**Response includes:**
- Total number of billionaires
- Combined wealth of top 10
- Top industry distribution
- Top country distribution

## Data Fields

| Field | Type | Description |
|-------|------|-------------|
| rank | integer | Position in the billionaires list |
| personName | string | Full name |
| finalWorth | float | Net worth in millions USD |
| age | integer | Age in years |
| countryOfCitizenship | string | Country of citizenship |
| source | string | Source of wealth |
| industries | array | Associated industries |
| organization | string | Primary company/organization |
| gender | string | Gender (M/F) |
| bios | array | Biography text snippets |
| squareImage | string | Profile image URL |
| uri | string | URI slug for profile URL |

## Notes

- **Net Worth**: The `finalWorth` field is in millions of USD. Divide by 1000 to get billions.
- **Pagination**: Use `offset` and `limit` parameters to paginate through the full list of 3,400+ billionaires.
- **Real-time Updates**: Forbes updates wealth figures throughout the year based on stock prices.
- **Historical Years**: You can specify different years (e.g., 2025, 2024) to access historical data.
- **Filtering**: Industry, country, and gender filters are applied client-side after fetching data.

## Use Cases

1. **Market Research**: Analyze wealth distribution by industry or country
2. **Journalism**: Find billionaires for story research
3. **Data Analysis**: Study wealth concentration and demographics
4. **Due Diligence**: Research individual profiles
5. **Trend Analysis**: Compare rankings across years

## Technical Implementation

The skill uses direct HTTP requests to Forbes' API endpoints:

- Uses `httpx` for async HTTP requests
- Supports pagination up to 500 records per request
- Implements client-side filtering for industry/country/gender
- Handles errors gracefully with structured error responses
- No browser automation required (fast and efficient)