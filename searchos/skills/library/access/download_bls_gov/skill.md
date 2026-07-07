# BLS State and Area Employment Data Downloader

This skill fetches and parses Bureau of Labor Statistics (BLS) State and Area Employment, Hours, and Earnings (SM) data files from the BLS public download server.

## Overview

The BLS provides bulk data downloads at `https://download.bls.gov/pub/time.series/sm/` containing:
- **sm.data.X.StateName**: Time series data files split by state
- **sm.series**: Series metadata and definitions
- **sm.area**: Geographic area codes and names
- **sm.industry**: Industry codes and titles
- **sm.data_type**: Data type codes (employment, hours, earnings)
- **sm.footnote**: Footnote codes and descriptions

## Data Format

All BLS bulk data files are **tab-delimited text files** with the following conventions:
- First line contains column headers
- Fields are separated by tabs (`\t`)
- Missing values represented by empty strings
- Numeric data includes decimal values with varying precision
- Series IDs follow BLS coding conventions

### sm.data.X.* Files (Time Series Data)

Columns:
- `series_id`: Unique series identifier (e.g., "SMU01000000000000001")
- `year`: 4-digit year (e.g., "2023")
- `period`: Time period code (M01-M12 for months, M13 for annual average, Q01-Q05 for quarters)
- `value`: Data value (numeric, can include decimals, "-" for missing)
- `footnote_codes`: Codes referencing footnote descriptions (optional)

### sm.series File (Series Metadata)

Columns include:
- `series_id`: Series identifier (matches data files)
- `area_code`: Geographic area code
- `supersector_code`: Supersector classification
- `industry_code`: Industry classification
- `data_type_code`: Type of data (employment, hours, earnings)
- `seasonal`: Seasonal adjustment indicator (S=seasonally adjusted, U=unadjusted)
- `series_title`: Human-readable title

## Series ID Structure

For SM (State and Metropolitan Area) series:
```
SM[U|S]AANNNNDDDDDTTTT
│ │ ││││ │││││ └─── Data type code (5 digits)
│ │ ││││ └────── Industry code (6 digits)  
│ │ └└└─────── Area code (FIPS state + area type)
│ └─────────── Seasonal indicator (U=unadjusted, S=adjusted)
└───────────── Survey prefix (SM)
```

## Functions

### `fetch_data_file`
Downloads a specific state data file. Returns parsed records with structured fields.

### `fetch_series_file`  
Downloads the series metadata file. Returns series definitions keyed by series_id.

### `fetch_area_codes`
Downloads the area codes reference file for geographic mapping.

### `fetch_industry_codes`
Downloads the industry codes reference file.

### `fetch_data_type_codes`
Downloads the data type codes reference file.

### `parse_series_id`
Analyzes a BLS series ID and extracts its component codes (area, industry, data type, seasonal adjustment).

## Usage Examples

```json
{
  "function": "fetch_data_file",
  "state": "Alabama"
}
```

```json
{
  "function": "fetch_data_file", 
  "file_path": "sm.data.1.Alabama"
}
```

```json
{
  "function": "fetch_series_file",
  "limit": 1000
}
```

## Error Handling

The skill handles:
- Network connection failures
- BLS server rate limiting (403 errors)
- Invalid state names or file paths
- Malformed data lines
- Missing or corrupted files

Returns structured error responses with:
- `error`: Boolean indicating failure
- `error_type`: Classification of the error
- `message`: Human-readable error description
- `partial_data`: Any data successfully retrieved before error

## Rate Limiting Note

BLS applies bot detection and rate limiting. If you receive 403 errors:
- Wait before retrying (recommended: 60+ seconds)
- Reduce request frequency
- Consider using the BLS API for smaller queries