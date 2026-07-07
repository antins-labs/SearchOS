# BLS Local Area Unemployment Statistics (LAUS) Access Skill

This skill retrieves unemployment data from the U.S. Bureau of Labor Statistics Local Area Unemployment Statistics (LAUS) database via the BLS Public API v2.

## Overview

The LAUS program produces monthly and annual employment, unemployment, and labor force data for census regions, divisions, states, counties, metropolitan areas, and many cities and towns.

## Data Available

- **Unemployment Rate (%)**: Percent of labor force that is unemployed
- **Unemployed (persons)**: Number of unemployed persons
- **Employment (persons)**: Number of employed persons  
- **Labor Force (persons)**: Total labor force (employed + unemployed)

## Geographic Coverage

- **States**: All 50 states + DC, Puerto Rico, Virgin Islands
- **Counties**: All 3,000+ U.S. counties
- **Metropolitan Areas**: Metropolitan Statistical Areas (MSAs)
- **Cities**: Many cities and towns

## Usage Examples

### Get State Unemployment Rate

```json
{
  "function": "get_state",
  "state": "CA",
  "measure": "03",
  "start_year": 2020,
  "end_year": 2024
}
```

Returns monthly unemployment rates for California from 2020-2024.

### Get Latest Rates for All States

```json
{
  "function": "get_latest_rates"
}
```

Returns the most recent unemployment rate for each state, sorted from lowest to highest.

### Get County Data

```json
{
  "function": "get_county",
  "state": "CA",
  "county_fips": "037",
  "measure": "03"
}
```

Returns unemployment data for Los Angeles County, CA (FIPS 06037).

### Search for State/County

```json
{
  "function": "search",
  "query": "California"
}
```

Returns matching states/counties with their series ID templates.

### Fetch Raw Series Data

```json
{
  "function": "fetch_series",
  "series_ids": ["LAUST060000000000003", "LAUST360000000000003"],
  "start_year": 2023,
  "end_year": 2024
}
```

Fetches data for specific BLS series IDs.

## Series ID Format

BLS LAUS series IDs follow this pattern:

```
LAU[AreaType][StateFIPS][AreaCode][Measure]
```

### Area Types
- **ST**: State
- **CN**: County
- **MT**: Metropolitan Statistical Area
- **MD**: Metropolitan Division

### State FIPS Codes
Two-digit codes: 01=Alabama, 06=California, 36=New York, 48=Texas, etc.

### Area Codes
- State-level: `0000000000` (10 zeros)
- County: 3-digit county code + `0000000` (7 zeros) for some series
- Metro area: Specific geographic codes

### Measure Codes
- **03**: Unemployment Rate (percent)
- **04**: Unemployed (persons)
- **05**: Employment (persons)
- **06**: Labor Force (persons)

### Example Series IDs
- `LAUST060000000000003`: California unemployment rate
- `LAUST360000000000003`: New York unemployment rate
- `LAUCN060370000000003`: Los Angeles County unemployment rate
- `LAUCN060010000000003`: Alameda County (CA) unemployment rate

## Response Format

Each data point includes:
- `year`: Year (e.g., "2024")
- `period`: Month code (e.g., "M01"=January, "M12"=December, "M13"=Annual Average)
- `periodName`: Month name (e.g., "January")
- `value`: Data value
- `footnotes`: Array of footnote objects with codes and explanations

## Rate Limits

- **Without API key**: 25 requests/day, 25 series per request
- **With API key**: 500 requests/day, 50 series per request

Get a free registration key at: https://api.bls.gov/RegistrationAPI/

## Common Footnotes

- **P**: Preliminary data
- **R**: Revised data
- **N**: Not available

## Data Updates

LAUS data is typically released:
- State/metropolitan data: Mid-month (e.g., March data released mid-April)
- County data: Approximately 2 weeks after state data

## Error Handling

The skill returns structured error information:
- `validation`: Invalid parameters (wrong state, measure, etc.)
- `rate_limit`: Daily API request limit exceeded
- `not_found`: Series does not exist
- `no_data`: Series exists but no data available for requested period
- `http_error`: Network/API communication error
- `timeout`: Request timed out

## Notes

1. The BLS website (www.bls.gov) has bot protection; this skill uses the official public API instead.
2. Data values are returned as strings from the API; convert to numbers as needed.
3. Annual averages are available as period "M13".
4. Historical data availability varies by geographic area; metropolitan and county data typically available from 1990 forward.