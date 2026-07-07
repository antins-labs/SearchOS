# FRED (Federal Reserve Economic Data) Access Skill

Access time series data and metadata from the Federal Reserve Bank of St. Louis's FRED database.

## Overview

FRED (Federal Reserve Economic Data) is one of the most comprehensive economic databases available, providing access to over 800,000 economic time series from various sources including:

- Federal Reserve Board
- Bureau of Labor Statistics (BLS)
- Bureau of Economic Analysis (BEA)
- U.S. Census Bureau
- Treasury Department
- And many more

## Available Functions

### get_series_data

Retrieve time series observations for a specific FRED series.

**Parameters:**
- `series_id` (required): FRED series identifier (e.g., 'GFDEBTN', 'GDP', 'UNRATE')
- `start_date` (optional): Start date filter (YYYY-MM-DD format)
- `end_date` (optional): End date filter (YYYY-MM-DD format)
- `transformation` (optional): Data transformation:
  - `lin`: Levels (default)
  - `chg`: Change
  - `ch1`: Change from Year Ago
  - `pch`: Percent Change
  - `pc1`: Percent Change from Year Ago
  - `pca`: Compounded Annual Rate of Change
  - `log`: Natural Log

**Example:**
```python
result = await execute({
    'function': 'get_series_data',
    'series_id': 'GFDEBTN',
    'start_date': '2020-01-01',
    'end_date': '2023-12-31'
})
# Returns: { success: true, series_id: 'GFDEBTN', observations: [...], observation_count: 16, ... }
```

### get_series_metadata

Retrieve comprehensive metadata for a FRED series.

**Parameters:**
- `series_id` (required): FRED series identifier

**Returns:**
- Series title and description
- Frequency (daily, weekly, monthly, quarterly, annual)
- Units (dollars, percent, index, etc.)
- Seasonal adjustment status
- Date range of available data
- Last updated timestamp
- Tags and keywords
- Category information
- Available transformations
- Source attribution

**Example:**
```python
result = await execute({
    'function': 'get_series_metadata',
    'series_id': 'GDP'
})
# Returns: { title: 'Gross Domestic Product', frequency: 'Quarterly', units: 'Billions of Dollars', ... }
```

### get_series_full

Retrieve both metadata and data in a single call.

**Parameters:**
- `series_id` (required): FRED series identifier
- `start_date`, `end_date` (optional): Date filters
- `transformation` (optional): Data transformation
- `include_observations` (optional): Include full observations array (default: true). If false, returns summary statistics instead.

**Example:**
```python
result = await execute({
    'function': 'get_series_full',
    'series_id': 'UNRATE',
    'start_date': '2023-01-01',
    'include_observations': false
})
# Returns metadata plus data summary (min/max/latest values)
```

### search_series

Search for FRED series by keyword.

**Parameters:**
- `query` (required): Search query string
- `limit` (optional): Maximum results (default: 20, max: 100)
- `offset` (optional): Pagination offset (default: 0)

**Example:**
```python
result = await execute({
    'function': 'search_series',
    'query': 'unemployment rate',
    'limit': 10
})
# Returns: { results: [{ series_id: 'UNRATE', title: 'Unemployment Rate', ... }] }
```

## Popular Series IDs

| Series ID | Description | Frequency |
|-----------|-------------|-----------|
| GDP | Gross Domestic Product | Quarterly |
| UNRATE | Unemployment Rate | Monthly |
| CPIAUCSL | Consumer Price Index | Monthly |
| GFDEBTN | Federal Debt: Total Public Debt | Quarterly |
| DFF | Federal Funds Effective Rate | Daily |
| HOUST | Housing Starts | Monthly |
| PAYEMS | Nonfarm Employment | Monthly |
| UMCSENT | Consumer Sentiment | Monthly |
| T10Y2Y | 10Y-2Y Treasury Spread | Daily |
| VIXCLS | VIX Volatility Index | Daily |

## Data Format

### Observations

Each observation contains:
- `date`: Date string in YYYY-MM-DD format
- `value`: Numeric value (or null if missing)

Missing values in FRED are represented as `.` and are converted to `null`.

### Date Handling

- Dates are returned in ISO format (YYYY-MM-DD)
- Most monthly/quarterly series use period-end dates
- Date filtering is applied after fetching data

## Transformation Options

FRED supports various data transformations that can be applied on the server:

| Code | Description | Use Case |
|------|-------------|----------|
| lin | Levels (no transformation) | Raw values |
| chg | Change | Period-over-period change |
| ch1 | Change from Year Ago | Year-over-year change |
| pch | Percent Change | Period-over-period growth rate |
| pc1 | Percent Change from Year Ago | Year-over-year growth rate |
| pca | Compounded Annual Rate | Annualized growth rate |
| log | Natural Log | For log-linear analysis |

## Use Cases

1. **Economic Analysis**: Track GDP, unemployment, inflation trends
2. **Financial Analysis**: Monitor interest rates, yield curves
3. **Policy Research**: Analyze federal debt, government spending
4. **Forecasting**: Access historical data for predictive models
5. **Dashboards**: Build real-time economic indicators

## Error Handling

The skill returns structured error responses:

```python
{
    'success': false,
    'error': 'Failed to fetch data (status 404)',
    'series_id': 'INVALID_ID'
}
```

Common errors:
- Series not found (invalid series_id)
- Request timeout
- Network errors

## Attribution

When using FRED data, please cite:
> Federal Reserve Bank of St. Louis. FRED Economic Data. https://fred.stlouisfed.org

## Rate Limits

The skill implements reasonable rate limiting:
- 10 requests per second
- 500 requests per minute

## Notes

- Series IDs are case-insensitive but typically uppercase
- Some series may have significant historical revisions
- Real-time data availability varies by series
- Vintage data (historical versions) is available for some series
- Data quality and timeliness varies by source