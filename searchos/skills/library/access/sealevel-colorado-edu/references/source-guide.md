# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Sea Level Research Group Access Skill

This skill provides access to global mean sea level (GMSL) time-series data from the University of Colorado Sea Level Research Group at [sealevel.colorado.edu](https://sealevel.colorado.edu).

## Overview

The Sea Level Research Group at the University of Colorado provides satellite altimetry-based global mean sea level data. This skill enables programmatic access to:

- Raw GMSL time-series data files
- Available data release versions
- Detailed release statistics and information

## Available Functions

### 1. `fetch_gmsl_timeseries`

Fetches Global Mean Sea Level time-series data with seasonal signals and Glacial Isostatic Adjustment (GIA) removed.

**Parameters:**
- `release` (string, optional): Data release version, e.g., "2026_rel1". Defaults to latest.
- `start_year` (integer, optional): Filter data from this year onwards
- `end_year` (integer, optional): Filter data up to this year
- `limit` (integer, optional): Maximum number of data points to return

**Returns:**
- Structured time-series data with decimal year, calendar year, day of year, and GMSL value in millimeters
- Summary statistics including min, max, mean, and year range
- Data source URL and release information

**Example:**
```json
{
  "function": "fetch_gmsl_timeseries",
  "release": "2026_rel1",
  "start_year": 2020,
  "end_year": 2025
}
```

### 2. `list_releases`

Lists all available data release versions from the data portal.

**Parameters:** None

**Returns:**
- List of all available release versions (sorted newest to oldest)
- Total count of releases
- The latest release version identifier

**Example:**
```json
{
  "function": "list_releases"
}
```

### 3. `get_release_info`

Gets detailed information about a specific data release, including temporal coverage, statistics, and sea level rise trends.

**Parameters:**
- `release` (string, optional): Release version, e.g., "2026_rel1". Defaults to latest.

**Returns:**
- Release header/description
- Data availability (start/end dates, total observations)
- Comprehensive statistics (min, max, mean, range, trend)
- Calculated linear trend in mm/year
- Total sea level rise over the observation period

**Example:**
```json
{
  "function": "get_release_info",
  "release": "2026_rel1"
}
```

## Data Description

The GMSL data represents global mean sea level derived from satellite altimetry measurements. Key characteristics:

- **Unit**: Millimeters (mm)
- **Processing**: Seasonal signals removed, GIA (Glacial Isostatic Adjustment) correction applied
- **Temporal resolution**: Approximately 10-day intervals
- **Coverage**: From 1992 (start of TOPEX/Poseidon mission) to present
- **Source**: Multi-mission satellite altimetry (TOPEX/Poseidon, Jason-1, Jason-2, Jason-3, Sentinel-6)

## Data Format

Each data point in the time-series contains:
- `decimal_year`: Year with fractional component (e.g., 2023.5)
- `year`: Calendar year
- `day_of_year`: Approximate day of year (1-365)
- `gmsl_mm`: Global mean sea level in millimeters

## Use Cases

1. **Climate Research**: Track long-term sea level rise trends
2. **Environmental Monitoring**: Assess coastal flood risk
3. **Scientific Analysis**: Calculate sea level rise rates and acceleration
4. **Data Integration**: Combine with other climate datasets

## Error Handling

All functions return a structured response with:
- `success`: Boolean indicating operation success
- `error`: Error message if operation failed
- Additional context (URL, release) for debugging

## Notes

- Data is updated periodically with new releases
- Each release may include recalibrated historical data
- The "seasons removed" variant is recommended for trend analysis
- GIA correction accounts for post-glacial rebound effects
