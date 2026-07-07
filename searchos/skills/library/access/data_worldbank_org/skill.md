# World Bank Open Data Access Skill

## Overview

This skill provides programmatic access to the World Bank Open Data API, enabling retrieval of development indicators, country statistics, and global economic data. The World Bank's data portal contains over 20,000 indicators covering topics like GDP, population, health, education, environment, and more across 200+ countries spanning 60+ years.

## API Details

- **Base URL**: `https://api.worldbank.org/v2`
- **Format**: JSON (default), XML, and downloadable formats available
- **Authentication**: Not required for public data
- **Rate Limit**: Generous limits (unofficially ~10 requests/second)

## Key Capabilities

### 1. Indicator Data Retrieval (`get_indicator_data`)
Fetch time series data for any indicator across countries and time periods.

**Popular Indicators:**
| Code | Description |
|------|-------------|
| NY.GDP.MKTP.CD | GDP (current US$) |
| NY.GDP.PCAP.CD | GDP per capita (current US$) |
| SP.POP.TOTL | Population, total |
| SP.URB.TOTL.IN.ZS | Urban population (% of total) |
| SH.DYN.MORT | Mortality rate, under-5 |
| SE.PRM.ENRR | School enrollment, primary |
| FP.CPI.TOTL.ZG | Inflation, consumer prices |

### 2. Country Information (`get_country`, `list_countries`)
Retrieve metadata for countries including income level, region, capital, and coordinates.

### 3. Indicator Discovery (`search`, `list_indicators`)
Search and browse indicators by keyword, topic, or source.

### 4. Data Comparison (`compare_countries`)
Compare indicators across multiple countries in a single query.

## Usage Examples

### Get GDP Data for a Country
```python
result = execute({
    "function": "get_indicator_data",
    "indicator_code": "NY.GDP.MKTP.CD",
    "countries": "US",
    "date": "2020:2024"
})
```

### Compare Multiple Countries
```python
result = execute({
    "function": "compare_countries",
    "indicator_code": "SP.POP.TOTL",
    "countries": ["US", "CN", "IN", "BR"],
    "date": "2023"
})
```

### Search for Indicators
```python
result = execute({
    "function": "search",
    "query": "illiteracy"
})
```

### Get Most Recent Values
```python
result = execute({
    "function": "get_indicator_data",
    "indicator_code": "SH.DYN.MORT",
    "mrv": 5  # Most recent 5 years of data
})
```

### List Countries by Income Level
```python
result = execute({
    "function": "list_countries",
    "income_level": "HIC"  # High Income Countries
})
```

## Response Structure

All API responses follow this format:
```json
[
  {
    "page": 1,
    "pages": 10,
    "per_page": 50,
    "total": 500
  },
  [
    { "indicator": {...}, "country": {...}, "date": "2023", "value": 12345.67 },
    ...
  ]
]
```

The first element contains pagination metadata, and the second element is the data array.

## Parameter Reference

### Country Codes
- ISO2 format: `US`, `CN`, `JP`, `DE`, `GB`, `FR`, `IN`, `BR`
- ISO3 format: `USA`, `CHN`, `JPN`, `DEU`, `GBR`, `FRA`, `IND`, `BRA`
- Multiple countries: Use semicolon separator (`US;CN;JP`) or array
- Special values: `all` for all countries/regions

### Date Formats
- Single year: `2023`
- Year range: `2020:2023`
- Most recent N values: Use `mrv` parameter instead of date

### Income Levels
- `HIC`: High income
- `UMC`: Upper middle income
- `LMC`: Lower middle income
- `LIC`: Low income

### Lending Types
- `IBD`: IBRD
- `IDA`: IDA
- `LNX`: Not classified

## Common Topics

| ID | Topic |
|----|-------|
| 1 | Agriculture & Rural Development |
| 2 | Aid Effectiveness |
| 3 | Economy & Growth |
| 4 | Education |
| 5 | Energy & Mining |
| 6 | Environment |
| 7 | Financial Sector |
| 8 | Gender |
| 9 | Health |
| 11 | Poverty |
| 12 | Private Sector |
| 13 | Public Sector |
| 14 | Science & Technology |
| 15 | Social Development |
| 16 | Social Protection & Labor |
| 19 | Urban Development |

## Notes

1. **Null Values**: The API returns `null` for data that is not available for a specific country/year combination.

2. **Pagination**: For large datasets, use the `fetch_all` parameter to automatically retrieve all pages, or manually paginate using the `page` parameter.

3. **Regional Data**: The API includes aggregate data for regions like "Africa Eastern and Southern", "Arab World", "Euro area", etc.

4. **Data Updates**: World Bank data is typically updated quarterly with annual releases for major indicators.

5. **Rate Limiting**: While the API is generous, implement reasonable delays for bulk requests to avoid rate limiting.

## Error Handling

The skill returns structured error responses:
```json
{
  "success": false,
  "error": "Resource not found",
  "status": 404
}
```

Common errors:
- `Resource not found` (404): Invalid indicator or country code
- `HTTP 400`: Invalid parameter format
- `Request failed`: Network or timeout issues

## Source Data

This skill interfaces with the World Bank Open Data API, which provides data from:
- World Development Indicators (WDI)
- International Debt Statistics
- Gender Statistics
- Education Statistics
- Health Nutrition and Population Statistics
- And 70+ other data sources