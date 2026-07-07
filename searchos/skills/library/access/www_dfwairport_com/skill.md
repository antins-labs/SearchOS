# DFW Airport Traffic Statistics Access Skill

This skill fetches traffic statistics from Dallas/Fort Worth International Airport's official website at [www.dfwairport.com/business/about/stats/](https://www.dfwairport.com/business/about/stats/).

## Overview

DFW Airport publishes monthly traffic statistics in three main categories:
- **Passenger Statistics** - Total passenger counts by month
- **Operations Statistics** - Aircraft operations (takeoffs and landings)
- **Cargo Statistics** - Cargo tonnage handled

All reports are published as PDF files, typically updated approximately 45 days after the close of each month. Historical data from 1982-2018 is available as an Excel archive.

## Available Functions

### get_all_statistics
Retrieves all available statistics reports across all categories.

```python
result = await execute({
    'function': 'get_all_statistics'
})
```

Returns a dictionary with four lists:
- `passenger_statistics` - List of passenger report PDFs
- `operations_statistics` - List of operations report PDFs  
- `cargo_statistics` - List of cargo report PDFs
- `archive` - Historical archives (1982-2018)

### get_passenger_statistics
Get only passenger statistics reports.

### get_operations_statistics
Get only operations statistics reports.

### get_cargo_statistics
Get only cargo statistics reports.

### get_latest_reports
Returns the most recent report from each category.

```python
result = await execute({
    'function': 'get_latest_reports'
})
```

### get_reports_by_period
Search for reports matching a specific time period.

```python
result = await execute({
    'function': 'get_reports_by_period',
    'period': 'Apr 26'  # Can also use "Dec 25", "2024", etc.
})
```

### get_page_info
Returns metadata about the statistics page including title, last update time, and the Next.js build ID.

## Report Structure

Each report entry contains:
- `title` - Full title (e.g., "Total Passengers: Apr 26")
- `type` - Report type (e.g., "Total Passengers", "Operations", "Total Cargo")
- `period` - Time period (e.g., "Apr 26")
- `url` - Direct link to the PDF report

## Technical Details

The DFW Airport website is built with Next.js using Static Site Generation (SSG). This skill:

1. Fetches the homepage to extract the current Next.js build ID
2. Uses the build ID to query the JSON data endpoint for the statistics page
3. Parses the markdown-formatted links from the page content
4. Returns structured data with clean URLs and metadata

## Data Source

All data is sourced from DFW Airport's official website. Reports are published by DFW Airport's business analytics team.

## Example Usage

```python
# Get all statistics
result = await execute({'function': 'get_all_statistics'})
for category, reports in result['data'].items():
    print(f"{category}: {len(reports)} reports")

# Find reports for a specific month
result = await execute({
    'function': 'get_reports_by_period',
    'period': 'April 2026'
})

# Get the latest reports
result = await execute({'function': 'get_latest_reports'})
latest = result['data']['latest_reports']
print(f"Latest passenger report: {latest['passenger_statistics']['url']}")
```