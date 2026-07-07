# World Bank API Access Skill

Fetch economic and development indicator data from the World Bank's official API.

## Overview

The World Bank API provides access to over 29,000 development indicators across 200+ countries and regions. This skill enables structured queries for economic, social, health, education, and environmental data.

## Features

### Get Indicator Data
Retrieve time-series data for specific indicators and countries:
- Single or multiple countries at once
- Date range filtering (start_year, end_year)
- Most-recent-value mode for latest data only
- Supports all 29,000+ indicators

### List Countries
Browse all countries/regions with metadata:
- Filter by income level (HIC, MIC, LIC)
- Filter by geographic region
- Filter by lending type
- Returns ISO codes, region, income level, capital city, coordinates

### List Indicators
Discover available indicators:
- Filter by data source (e.g., World Development Indicators)
- Filter by topic area
- Returns indicator name, description, source, and source notes

### Get Country/Indicator Info
Detailed metadata for specific countries or indicators.

## Common Indicator Codes

| Code | Description |
|------|-------------|
| `NY.GDP.MKTP.CD` | GDP (current US$) |
| `NY.GDP.MKTP.KD.ZG` | GDP growth (annual %) |
| `SP.POP.TOTL` | Population, total |
| `SP.POP.GROW` | Population growth (annual %) |
| `MS.MIL.XPND.CD` | Military expenditure (current USD) |
| `MS.MIL.XPND.GD.ZS` | Military expenditure (% of GDP) |
| `SE.XPD.TOTL.GD.ZS` | Education expenditure (% of GDP) |
| `SH.XPD.CHEX.GD.ZS` | Health expenditure (% of GDP) |
| `EN.ATM.CO2E.KT` | CO2 emissions (kt) |
| `EG.USE.ELEC.KH.PC` | Electric power consumption (kWh per capita) |

## Usage Examples

### Example 1: Get US GDP data
```json
{
  "function": "get_indicator_data",
  "country_codes": ["US"],
  "indicator_code": "NY.GDP.MKTP.CD",
  "start_year": 2020,
  "end_year": 2024
}
```

### Example 2: Get latest GDP for multiple countries
```json
{
  "function": "get_indicator_data",
  "country_codes": ["US", "CN", "JP", "DE", "GB"],
  "indicator_code": "NY.GDP.MKTP.CD",
  "most_recent_only": true
}
```

### Example 3: Get military expenditure for all countries
```json
{
  "function": "get_indicator_data",
  "country_codes": ["all"],
  "indicator_code": "MS.MIL.XPND.CD",
  "most_recent_only": true
}
```

### Example 4: List high-income countries
```json
{
  "function": "list_countries",
  "income_level": "HIC"
}
```

### Example 5: Search for GDP-related indicators
```json
{
  "function": "list_indicators",
  "source": 2,
  "per_page": 50
}
```

### Example 6: Get indicator details
```json
{
  "function": "get_indicator_info",
  "indicator_code": "NY.GDP.MKTP.CD"
}
```

### Example 7: Get country details
```json
{
  "function": "get_country_info",
  "country_code": "US"
}
```

## Response Format

### Indicator Data Response
```json
{
  "success": true,
  "data": {
    "indicator": {
      "id": "NY.GDP.MKTP.CD",
      "value": "GDP (current US$)"
    },
    "pagination": {
      "page": 1,
      "pages": 1,
      "total": 4
    },
    "records": [
      {
        "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP (current US$)"},
        "country": {"id": "US", "value": "United States"},
        "countryiso3code": "USA",
        "date": "2024",
        "value": 28750956130731.2,
        "unit": "",
        "obs_status": "",
        "decimal": 0
      }
    ],
    "record_count": 1
  }
}
```

### Country List Response
```json
{
  "success": true,
  "data": {
    "countries": [
      {
        "id": "US",
        "iso2Code": "US",
        "name": "United States",
        "region": {"id": "NAC", "value": "North America"},
        "incomeLevel": {"id": "HIC", "value": "High income"},
        "capitalCity": "Washington D.C.",
        "longitude": "-77.032",
        "latitude": "38.8895"
      }
    ],
    "total": 1
  }
}
```

## Error Handling

The skill returns structured error responses instead of raising exceptions:

```json
{
  "success": false,
  "error": "Invalid value: The provided parameter value is not valid"
}
```

Common errors:
- Invalid country code: Returns API-level error message
- Invalid indicator code: Returns API-level error message
- Missing required parameter: Returns validation error
- Network timeout: Returns timeout error

## API Notes

- **Rate Limiting**: The World Bank API has generous rate limits but requires a `format=json` parameter for JSON responses
- **Default Format**: Without `format=json`, the API returns XML
- **Pagination**: Large result sets are paginated (default 50 items per page, max configurable per request)
- **Missing Data**: `value` field may be `null` for years without data
- **Country Codes**: Supports both 2-letter (ISO 3166-1 alpha-2) and 3-letter (ISO 3166-1 alpha-3) codes
- **Aggregations**: Some "countries" are actually regional aggregations (e.g., "WLD" for World, "EUU" for European Union)