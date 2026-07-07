# Edmunds.com Vehicle Data Access Skill

## Overview

This skill retrieves vehicle specifications, trim levels, and feature information from Edmunds.com, a comprehensive automotive research website. It accesses vehicle data pages to extract:

- Vehicle specifications (engine, transmission, dimensions, fuel economy)
- Trim level comparisons and differences
- Standard and optional features by trim
- Pricing information (MSRP, invoice)

## Available Functions

### get_features_specs

Fetches detailed vehicle specifications including:
- Engine specifications (displacement, horsepower, torque)
- Transmission details
- Fuel economy ratings
- Exterior and interior dimensions
- Cargo capacity
- Towing capacity (if applicable)
- Safety features

### get_trims

Retrieves all available trim levels for a vehicle, including:
- Trim names and identifiers
- Base MSRP for each trim
- Key differentiating features
- Available packages

### get_vehicle_data

General vehicle data retrieval that defaults to specifications data.

## Usage

### Required Parameters

- `make`: Vehicle brand name (lowercase), e.g., `nissan`, `buick`, `lexus`
- `model`: Vehicle model name (lowercase), e.g., `sentra`, `envision`, `nx`
- `year`: Model year, e.g., `2025`, `2024`

### Example Requests

```json
{
  "function": "get_features_specs",
  "make": "nissan",
  "model": "sentra",
  "year": "2025"
}
```

```json
{
  "function": "get_trims",
  "make": "buick",
  "model": "envision",
  "year": "2025"
}
```

```json
{
  "function": "get_trims",
  "make": "lexus",
  "model": "nx",
  "year": "2025"
}
```

### Response Format

```json
{
  "success": true,
  "blocked": false,
  "source": "edmunds",
  "url": "https://www.edmunds.com/nissan/sentra/2025/features-specs/",
  "make": "Nissan",
  "model": "Sentra",
  "year": "2025",
  "page_type": "features-specs",
  "data": {
    "make": "Nissan",
    "model": "Sentra",
    "year": "2025",
    "trims": [
      {"name": "S", "msrp": 21990, "id": "..."},
      {"name": "SV", "msrp": 23990, "id": "..."},
      {"name": "SR", "msrp": 25190, "id": "..."}
    ],
    "specifications": {
      "engine": "2.0L I-4",
      "horsepower": "149 hp",
      "transmission": "CVT",
      "fuel_economy_city": "30 mpg",
      "fuel_economy_hwy": "40 mpg"
    },
    "features": {},
    "pricing": {}
  },
  "error": null
}
```

## Error Handling

The skill returns structured error information:

### Blocked Access (403 Forbidden)

```json
{
  "success": false,
  "blocked": true,
  "error": "Access blocked by Edmunds (403 Forbidden)",
  "url": "..."
}
```

Edmunds.com has strong anti-bot protections. If access is blocked:
- The skill returns `blocked: true`
- The error message explains the blocking
- Data cannot be retrieved in this case

### Invalid Parameters

```json
{
  "success": false,
  "error": "Missing required parameter: make"
}
```

## Data Extraction

The skill uses multiple methods to extract data:

1. **Primary**: Extracts from `__NEXT_DATA__` script tag containing Next.js page props
2. **Secondary**: Parses page elements if __NEXT_DATA__ is unavailable
3. **Fallback**: Searches for spec tables and trim listings in the DOM

## Supported Vehicles

Any vehicle available on Edmunds.com with a valid:
- Make/model URL structure
- Year within the vehicle's production range
- Edmunds features-specs or trims page

## Technical Notes

### Anti-Bot Protections

Edmunds.com employs aggressive bot detection:
- 403 Forbidden responses for automated requests
- Browser fingerprinting detection
- JavaScript-based challenges

This skill uses Playwright with anti-detection measures, but blocking may still occur.

### Rate Limiting

To avoid being blocked:
- Requests include delays between calls
- Browser context is reused when possible
- Realistic headers and user agents are used

### Data Availability

Data availability depends on:
- Vehicle being listed on Edmunds
- Year being within supported range
- Edmunds having populated data for the trim/specs

## Source URLs

The skill accesses URLs in the format:
- `{make}/{model}/{year}/features-specs/`
- `{make}/{model}/{year}/trims/`

Example:
- `https://www.edmunds.com/nissan/sentra/2025/features-specs/`
- `https://www.edmunds.com/buick/envision/2025/trims/`
- `https://www.edmunds.com/lexus/nx/2025/trims/`