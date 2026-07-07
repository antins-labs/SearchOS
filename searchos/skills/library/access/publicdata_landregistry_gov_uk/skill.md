# UK Land Registry House Price Index Data

This skill provides access to the UK Land Registry's public house price index data from
`publicdata.landregistry.gov.uk`. It efficiently handles large CSV files (150K+ rows)
with streaming and filtering capabilities.

## Data Types

Two data types are available:

### 1. Average Prices (`average-prices`)
Contains monthly average house prices by region with the following columns:
- **Date**: Monthly date (YYYY-MM-DD format)
- **Region_Name**: Geographic area name (405 regions including countries, counties, boroughs)
- **Area_Code**: Official area code (e.g., E92000001 for England)
- **Average_Price**: Average house price in GBP
- **Monthly_Change**: Percentage change from previous month
- **Annual_Change**: Percentage change from same month last year
- **Average_Price_SA**: Seasonally adjusted average price

### 2. Sales Volume (`sales`)
Contains monthly sales transaction counts:
- **Date**: Monthly date
- **Region_Name**: Geographic area name
- **Area_Code**: Official area code
- **Sales_Volume**: Number of property sales

## Regional Coverage

Data covers 405 regions including:
- Countries: England, Wales, Scotland, Northern Ireland, United Kingdom
- Regions: London, South East, North West, etc.
- Counties and Local Authorities: All UK counties and boroughs
- Aggregate areas: Great Britain, England and Wales

## Available Functions

### get_data
Fetch filtered data from a specific month.

Example: Get London prices for 2026-02:
```json
{
  "function": "get_data",
  "year_month": "2026-02",
  "data_type": "average-prices",
  "region_exact": "London"
}
```

Example: Get all regions with prices over £500,000:
```json
{
  "function": "get_data",
  "year_month": "2026-02",
  "min_price": 500000
}
```

Example: Get data for a specific date range within the file:
```json
{
  "function": "get_data",
  "year_month": "2026-02",
  "region": "Manchester",
  "date_from": "2024-01-01",
  "date_to": "2024-12-31"
}
```

### list_regions
List all available regions and their area codes.

Example:
```json
{
  "function": "list_regions",
  "year_month": "2026-02"
}
```

Example with search:
```json
{
  "function": "list_regions",
  "year_month": "2026-02",
  "search": "london"
}
```

### get_metadata
Get file metadata including row count, date range, and columns.

Example:
```json
{
  "function": "get_metadata",
  "year_month": "2026-02"
}
```

### get_timeseries
Get time series data for a region across multiple months.

Example:
```json
{
  "function": "get_timeseries",
  "region": "London",
  "months": ["2025-01", "2025-02", "2025-03", "2025-04"]
}
```

Example: Get latest 6 months automatically:
```json
{
  "function": "get_timeseries",
  "region": "Manchester",
  "latest_n": 6
}
```

## Data Notes

- **Historical Depth**: Data goes back to 1968 for some regions
- **Update Frequency**: New data is typically released 2-3 months after the reference month
- **File Size**: Full CSV files contain ~150,000 rows (~7MB uncompressed)
- **Filtering**: Use filters (region, date range, price limits) to get manageable result sets
- **Pagination**: Use `limit` and `offset` parameters for large result sets

## Example Region Names

- Countries: England, Wales, Scotland, Northern Ireland
- Regions: London, South East, North West, East of England
- Cities: Birmingham, Manchester, Leeds, Sheffield
- London Boroughs: Camden, Westminster, Kensington and Chelsea
- Counties: Kent, Essex, Lancashire, Yorkshire

## Performance Tips

1. Always use filters when possible - the full files contain 150K+ rows
2. Use `region_exact` for exact matches, `region` for partial matches
3. Use `limit` to cap results (default is 100, maximum is 10,000)
4. Use `get_metadata` first to understand file structure
5. Use `list_regions` with `search` to find area codes