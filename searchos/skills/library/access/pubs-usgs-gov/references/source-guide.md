# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# USGS Mineral Commodity Summaries PDF Extractor

This skill extracts structured mineral commodity statistics from the U.S. Geological Survey's Mineral Commodity Summaries 2025 publications hosted at pubs.usgs.gov.

## Overview

The USGS Mineral Commodity Summaries (MCS) is an annual publication providing essential statistics on about 90 mineral commodities. This skill parses the PDF documents to extract:

- Production statistics (mine, refinery, imports, exports)
- Price data by commodity grade
- World mine production and reserves by country
- Import sources and tariffs
- Recycling and substitute information

## Functions

### list_commodities
Returns a list of all available mineral commodities in the MCS 2025 report with their page numbers.

**Example:**
```json
{"function": "list_commodities"}
```

### get_commodity
Extracts detailed statistics for a specific mineral commodity.

**Parameters:**
- `commodity` (required): The mineral name (e.g., "Copper", "Rare Earths", "Lithium", "Gold")

**Example:**
```json
{"function": "get_commodity", "commodity": "Copper"}
```

### get_rare_earths
Provides detailed extraction of the Rare Earths commodity with parsed tables including salient statistics, prices, and world production data.

**Example:**
```json
{"function": "get_rare_earths"}
```

### get_full_info
Returns metadata about the complete MCS 2025 PDF file.

**Example:**
```json
{"function": "get_full_info"}
```

## Data Structure

### Commodity Data Returns

```json
{
  "commodity": "Copper",
  "prepared_by": "Daniel M. Flanagan",
  "contact": "(703) 648-7726, dflanagan@usgs.gov",
  "data_unit": "thousand metric tons, copper content",
  "domestic_production_and_use": "...",
  "salient_statistics": {
    "years": ["2020", "2021", "2022", "2023", "2024e"],
    "data": {
      "Production": {
        "Mine, recoverable": ["1,200", "1,230", "1,230", "1,130", "1,100"]
      }
    }
  },
  "world_production": [
    {
      "country": "United States",
      "production_2023": "1,130",
      "production_2024": "1,100",
      "reserves": "50,000,000"
    }
  ],
  "prices": {...},
  "import_sources": "...",
  "tariff": "...",
  "recycling": "...",
  "resources": "...",
  "substitutes": "..."
}
```

## Supported Commodities

The MCS 2025 includes approximately 90 mineral commodities including:

- **Metals**: Aluminum, Copper, Gold, Iron, Lead, Lithium, Nickel, Silver, Zinc, etc.
- **Industrial Minerals**: Barite, Cement, Clays, Gypsum, Salt, Sand & Gravel, etc.
- **Rare Elements**: Rare Earths, Gallium, Germanium, Indium, Rhenium, etc.
- **Energy Minerals**: Helium, Uranium (if applicable)

## Source

U.S. Geological Survey, Mineral Commodity Summaries 2025
https://pubs.usgs.gov/periodicals/mcs2025/

## Notes

- Data units vary by commodity (metric tons, thousand metric tons, kilograms, etc.)
- The "e" suffix in years (e.g., "2024e") indicates estimated values
- Some commodities span multiple pages
- World production tables include country-by-country breakdowns
- Price data includes multiple grades/specifications where applicable
