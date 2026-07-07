# ATL (Hartsfield-Jackson Atlanta International Airport) Operating Statistics

Access airport operating statistics from the world's busiest airport by passenger traffic.

## Overview

This skill provides access to monthly operating statistics reports from Hartsfield-Jackson Atlanta International Airport (ATL). The reports include:

- **Passenger Statistics**: Domestic and international passenger counts (on/off)
- **Aircraft Operations**: Air carrier, air taxi, general aviation, and military operations
- **Cargo Data**: Freight, express, and mail tonnage (metric tons)
- **Carrier Breakdown**: Detailed statistics by airline

## Available Functions

### `list_statistics`

List available monthly operating statistics reports with PDF download links.

**Parameters**:
- `year` (optional): Filter by specific year (2013-2026). Returns all years if not specified.
- `with_details` (optional): Include PDF download status check (slower)

**Example**:
```python
# List all available reports
result = await execute({"function": "list_statistics"}, ctx)

# List reports for a specific year
result = await execute({"function": "list_statistics", "year": 2024}, ctx)
```

**Returns**:
```json
{
  "available_years": [2026, 2025, 2024, ...],
  "total_reports": 156,
  "reports": {
    "2025": {
      "months": [
        {"month": 1, "month_name": "Jan", "pdf_url": "https://..."},
        {"month": 2, "month_name": "Feb", "pdf_url": "https://..."},
        ...
      ]
    }
  }
}
```

### `get_pdf_data`

Download and extract structured data from a specific monthly statistics PDF.

**Parameters**:
- `pdf_url` (optional): Direct PDF URL
- `year` (optional): Year of the report (e.g., 2025) - used with month
- `month` (optional): Month of the report (1-12) - used with year

**Example**:
```python
# Get report by year/month
result = await execute({
    "function": "get_pdf_data",
    "year": 2025,
    "month": 1
}, ctx)

# Get report by URL
result = await execute({
    "function": "get_pdf_data",
    "pdf_url": "https://www.atl.com/wp-content/uploads/2026/02/ATL-ATR-2501_revF.pdf"
}, ctx)
```

**Returns**:
```json
{
  "title": "Monthly Airport Traffic Report - January 2025",
  "month": "January",
  "year": 2025,
  "passengers": [
    {"category": "Domestic On", "current": 3179463, "previous": 3281120},
    {"category": "Domestic Off", "current": 3214095, "previous": 3320633},
    {"category": "International On", "current": 551777, "previous": 522150},
    {"category": "International Off", "current": 596868, "previous": 560304}
  ],
  "aircraft_operations": [
    {"category": "Air Carrier", "current": 52977, "previous": 54054},
    {"category": "Air Taxi", "current": 6718, "previous": 599},
    {"category": "General Aviation", "current": 836, "previous": 859},
    {"category": "Military", "current": 157, "previous": 114}
  ],
  "cargo": {
    "freight": {"current": 47845, "previous": 51448},
    "mail": {"current": 1608, "previous": 716},
    "total": {"current": 49453, "previous": 52164}
  },
  "page_count": 3,
  "pdf_url": "https://...",
  "pdf_size_bytes": 250457
}
```

### `get_latest_report`

Get the most recent monthly operating statistics report with full data extraction.

**Example**:
```python
result = await execute({"function": "get_latest_report"}, ctx)
```

Returns the same structure as `get_pdf_data` for the most recent available month.

### `get_page_content`

Get the raw content summary of the statistics page (useful for debugging).

**Example**:
```python
result = await execute({"function": "get_page_content"}, ctx)
```

## Data Notes

### PDF Downloads
The statistics PDFs are protected and require browser-like requests to download. This skill uses Playwright to download PDFs, which may be slightly slower than direct HTTP requests but ensures reliable access.

### Report Structure
Each monthly PDF contains 3 pages:
1. **Page 1**: Summary statistics - passengers, aircraft operations, cargo totals
2. **Page 2**: Carrier-specific passenger data - breakdown by airline
3. **Page 3**: Carrier-specific cargo/freight data

### Year-over-Year Comparison
The reports include "previous" values for year-over-year comparison. These are typically the same month from the previous year.

### Data Categories

**Passengers**:
- Domestic On: Passengers boarding domestic flights
- Domestic Off: Passengers deplaning domestic flights
- International On: Passengers boarding international flights
- International Off: Passengers deplaning international flights

**Aircraft Operations**:
- Air Carrier: Major airline operations
- Air Taxi: Regional/commuter operations
- General Aviation: Private/recreational flights
- Military: Military aircraft operations

**Cargo (Metric Tons)**:
- Freight & Express: Commercial cargo
- Mail: Postal service cargo

## Source

Data is sourced from the official ATL website:
https://www.atl.com/business-information/statistics/

The reports are published by the Department of Aviation, Hartsfield-Jackson Atlanta International Airport, Atlanta, Georgia.

## Rate Limiting & Caching

- The skill internally fetches the statistics page to find PDF URLs
- PDFs are downloaded on-demand and not cached
- Consider caching responses when frequently querying historical data
- Large PDFs (~250KB) may take a few seconds to download and parse