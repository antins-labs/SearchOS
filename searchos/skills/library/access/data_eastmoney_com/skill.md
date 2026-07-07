# East Money Financial Data Center (data.eastmoney.com)

Access financial and industry statistics from East Money's comprehensive data portal.

## Overview

East Money (东方财富网) is one of China's largest financial information platforms. Their data center provides access to thousands of economic indicators, industry statistics, and market data including:

- Transportation metrics (railway passenger volume, civil aviation data, port throughput)
- Industry indices and price indices
- Macroeconomic indicators
- Sector-specific statistics

This skill enables direct API access to retrieve structured time series data without needing to scrape the web interface.

## Available Functions

### 1. `get_data` - Get Indicator Time Series Data

Retrieve historical data for a specific indicator.

```python
params = {
    "function": "get_data",
    "indicator_id": "EMI00106130",  # Railway Passenger Volume
    "page_size": 50,
    "page_number": 1
}
```

**Returns:**
- `data`: List of time series records with:
  - `date`: Report date (YYYY-MM-DD)
  - `value`: Indicator value
  - `change_rate`: Period change rate (%)
  - `change_rate_3m`: 3-month change rate (%)
  - `change_rate_6m`: 6-month change rate (%)
  - `change_rate_1y`: 1-year change rate (%)
  - `change_rate_2y`: 2-year change rate (%)
  - `change_rate_3y`: 3-year change rate (%)
- `total_pages`: Total number of pages available
- `total_count`: Total number of records

### 2. `list_indicators` - List Available Indicators

Get a list of available indicators with their latest values.

```python
params = {
    "function": "list_indicators",
    "page_size": 100,
    "page_number": 1
}
```

**Returns:**
- `indicators`: List of indicators with:
  - `indicator_id`: Unique identifier
  - `indicator_name`: Chinese name
  - `board_name`: Category/sector name
  - `latest_date`: Most recent data date
  - `latest_value`: Most recent value
  - `change_rate`: Change rate (%)

### 3. `search` - Search Indicators

Search for indicators by keyword.

```python
params = {
    "function": "search",
    "keyword": "客运"  # Search for indicators containing "passenger transport"
}
```

**Returns:**
- `total_matches`: Number of matching indicators
- `indicators`: List of matching indicators with details

### 4. `get_info` - Get Indicator Metadata

Get detailed information about a specific indicator.

```python
params = {
    "function": "get_info",
    "indicator_id": "EMI00106130"
}
```

**Returns:**
- `indicator_name`: Full name of the indicator
- `latest_date`: Most recent data date
- `latest_value`: Most recent value
- `total_records`: Number of historical records available
- Change rates for various periods

## Common Indicator IDs

| ID | Name | Category |
|----|------|----------|
| EMI00106130 | 铁路客运量:当月值 | Transportation |
| EMI00108735 | 民航客运量:当月值 | Transportation |
| EMI00108768 | 民航货运量:当月值 | Transportation |
| EMI00135323 | 社会消费品零售总额:当月值 | Consumption |
| EMI00108258 | 全国主要港口:货物吞吐量 | Trade |
| EMI00108261 | 全国主要港口:旅客吞吐量 | Trade |

## Example Usage

```python
# Get railway passenger volume data for the last 12 months
result = await execute({
    "function": "get_data",
    "indicator_id": "EMI00106130",
    "page_size": 12
})

# Search for aviation-related indicators
result = await execute({
    "function": "search",
    "keyword": "民航"
})

# Get metadata about railway passenger volume
result = await execute({
    "function": "get_info",
    "indicator_id": "EMI00106130"
})
```

## Notes

- Data is typically updated monthly
- Historical data may span several years (often 10+ years)
- Change rates are calculated as percentage changes from the same period
- All monetary values are in Chinese Yuan unless otherwise specified
- Some indicators may have data gaps or discontinued series

## Error Handling

All functions return:
- `success`: Boolean indicating if the operation succeeded
- `error`: Error message (only present when success is False)
- Data fields (only present when success is True)