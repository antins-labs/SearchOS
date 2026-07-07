# HKEX Monthly Market Highlights

## Overview

This skill fetches Hong Kong Stock Exchange (HKEX) monthly market statistics from the HKEX Monthly Market Highlights page. It provides access to comprehensive securities and derivatives market data updated monthly.

## Data Available

The skill extracts the following market statistics:

### Securities Market
- Number of listed companies and securities
- Total market capitalization
- Newly listed companies
- SPAC shares and warrants

### Market Turnover
- Monthly and average daily turnover
- Trading days count
- Turnover by securities type (equities, derivatives warrants, CBBCs, unit trusts/ETFs)

### Stock Connect
- Northbound average daily turnover (RMB)
- Southbound average daily turnover (HKD)
- Trading days

### Mainland Enterprises
- H shares count
- Non-H share mainland enterprises
- Market capitalization percentage
- Turnover percentage

### Indices
- S&P/HKEX LargeCap Index
- Hang Seng Index
- Hang Seng China Enterprises Index
- And others with monthly and 12-month changes

### Derivatives Market
- Futures and options trading volumes
- Average daily volumes by product type

### Historical Records
- HSI record highs
- Top turnover days
- Top market capitalization days
- Record derivatives volumes

## Functions

### list_months
Lists all available months with their GUIDs for data retrieval.

```python
result = await execute({'function': 'list_months'})
# Returns: {'success': True, 'months': [{'month': 'May 2026', 'guid': '{...}'}, ...]}
```

### get_highlights
Fetches structured market highlights for a specific month.

```python
# Get latest month
result = await execute({'function': 'get_highlights'})

# Get specific month by name
result = await execute({'function': 'get_highlights', 'month': 'May 2025'})

# Get specific month by GUID
result = await execute({'function': 'get_highlights', 'month_guid': '{...}'})
```

Returns:
- `month`: The month of the data
- `data`: Structured data organized by category (listed_securities, turnover, stock_connect, etc.)
- `raw_tables`: Original table data

### get_raw_tables
Fetches raw table data without structure mapping.

```python
result = await execute({'function': 'get_raw_tables', 'month': 'April 2026'})
```

## Output Structure

```json
{
  "success": true,
  "month": "May 2025",
  "month_guid": "{5B984B00-9551-4A5B-B3A4-4AFD16B70E88}",
  "data": {
    "listed_securities": {
      "No. of listed companies": {
        "current": "2,633",
        "previous": "2,610",
        "year_end": "2,631"
      },
      ...
    },
    "turnover": { ... },
    "stock_connect": { ... },
    "mainland_enterprises": { ... },
    "indices": { ... },
    "derivatives": { ... }
  },
  "raw_tables": [ ... ],
  "table_count": 16
}
```

## Technical Details

- **Data Source**: https://www.hkex.com.hk/Market-Data/Statistics/Consolidated-Reports/HKEX-Monthly-Market-Highlights
- **Method**: HTML parsing with BeautifulSoup
- **Month Selection**: Uses URL parameter `select={GUID}` to select specific months
- **Rate Limiting**: Please respect HKEX's servers with reasonable request intervals

## Known Limitations

- Historical data availability depends on what HKEX has published on their website
- GUIDs may change if HKEX updates their internal content management system
- No API available; data is extracted from HTML tables