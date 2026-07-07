# MBA Lib Wiki - Fortune Global 500 Access Skill

Access Fortune Global 500 rankings data from MBA Lib Wiki (wiki.mbalib.com).

## Overview

This skill provides structured access to Fortune Global 500 company rankings published on MBA Lib Wiki. It extracts data from the wikitable on Chinese-language pages, supporting both Traditional (zh-tw) and Simplified (zh-cn) Chinese variants.

## Important Note on Table Formats

The table format varies by year:
- **2024**: 5 columns (rank, company, revenue, profit, country) - Full financial data
- **2023**: 3 columns (rank, company, country) - Simplified format without financials
- **2022**: 6 columns (rank, company, revenue, profit, country, key_data) - Full + extra data

The skill automatically detects the format and returns available fields. Revenue and profit fields will be `null` for years where that data is unavailable.

## Data Fields

Each company entry includes:
- **rank**: Position in Fortune 500 (1-500)
- **company_name**: Chinese name with English name in parentheses (when available)
- **revenue_millions_usd**: Revenue in millions of USD (null for 2023)
- **profit_millions_usd**: Profit in millions of USD (null for 2023)
- **country**: Country of origin (in Chinese)

## Functions

### `get_fortune_500`
Get the complete Fortune 500 list with optional pagination.

Parameters:
- `year` (int, default: 2024): Year of the Fortune 500 list
- `lang` (string, default: 'zh-tw'): Language variant ('zh-tw' or 'zh-cn')
- `limit` (int, optional): Maximum entries to return
- `offset` (int, default: 0): Entries to skip for pagination

Returns:
- `companies`: List of company entries
- `total_companies`: Total number (usually 500)
- `returned_count`: Number of entries returned
- `table_headers`: Column headers from the source table
- `has_financial_data`: Boolean indicating if revenue/profit data is available

### `get_by_rank`
Get a company at a specific rank position.

Parameters:
- `rank` (int, required): Rank position (1-500)
- `year` (int, default: 2024)
- `lang` (string, default: 'zh-tw')

Returns:
- `company`: Single company entry

### `search_by_company`
Search for companies by name (partial match, case-insensitive).

Parameters:
- `query` (string, required): Company name search query
- `year` (int, default: 2024)
- `lang` (string, default: 'zh-tw')
- `limit` (int, default: 20): Maximum results

Returns:
- `results`: List of matching companies
- `total_matches`: Total number of matches

### `get_by_country`
Get all companies from a specific country.

Parameters:
- `country` (string, required): Country name (e.g., '美國', '中國', '日本')
- `year` (int, default: 2024)
- `lang` (string, default: 'zh-tw')

Returns:
- `companies`: List of companies from that country, sorted by rank
- `total_companies`: Count of companies from that country

### `list_countries`
Get country distribution with company counts.

Parameters:
- `year` (int, default: 2024)
- `lang` (string, default: 'zh-tw')

Returns:
- `countries`: Dictionary mapping country names to counts, sorted by count descending
- `total_countries`: Number of distinct countries

## Examples

### Get Top 10 Companies in 2024

```python
result = await execute({
    "function": "get_fortune_500",
    "year": 2024,
    "limit": 10
})
```

Returns:
```json
{
  "success": true,
  "year": 2024,
  "total_companies": 500,
  "returned_count": 10,
  "has_financial_data": true,
  "companies": [
    {
      "rank": 1,
      "company_name": "沃爾瑪(WALMART)",
      "revenue_millions_usd": "648,125",
      "profit_millions_usd": "15,511",
      "country": "美國"
    },
    ...
  ]
}
```

### Get 2023 Data (No Financials)

```python
result = await execute({
    "function": "get_fortune_500",
    "year": 2023,
    "limit": 5
})
```

Returns companies without revenue/profit data for 2023.

### Search for Apple

```python
result = await execute({
    "function": "search_by_company",
    "query": "蘋果"
})
```

### Get US Companies

```python
result = await execute({
    "function": "get_by_country",
    "country": "美國"
})
```

### Get Country Distribution

```python
result = await execute({
    "function": "list_countries"
})
```

Returns:
```json
{
  "success": true,
  "countries": {
    "美國": 139,
    "中國": 133,
    "日本": 40,
    "德國": 29,
    "法國": 24,
    ...
  }
}
```

## Technical Details

### Data Source
- **Host**: wiki.mbalib.com
- **URL Pattern**: `https://wiki.mbalib.com/{lang}/{year}年《财富》世界500强`
- **Method**: Direct HTTP fetch with HTML parsing using lxml
- **No browser automation required**: The page renders HTML server-side

### Implementation
- Uses `httpx` for HTTP requests
- Uses `lxml.html` for HTML parsing
- Parses `<table class="wikitable">` elements
- Handles variable column formats (3, 5, or 6 columns)
- No authentication required
- No rate limiting detected (but be respectful)

### Available Years
- 2024: Full financial data (5 columns)
- 2023: Simplified (3 columns - no financials)
- 2022: Full financial data + key_data (6 columns)
- Earlier years may be available at similar URLs

### Language Variants
- `zh-tw`: Traditional Chinese (Taiwan)
- `zh-cn`: Simplified Chinese (Mainland China)

## Notes

- The page was opened 39 times with zero evidence in the generic reader, indicating the table extraction was problematic
- This skill uses direct HTML parsing to reliably extract the structured table data
- Revenue and profit figures are formatted with commas (e.g., "648,125") and are in millions of USD