# SIPRI Military Expenditure and Arms Database Access Skill

## Overview

This skill provides programmatic access to the Stockholm International Peace Research Institute (SIPRI) databases, focusing on military expenditure, arms industry, and arms transfers data. Unlike the original probe findings that showed "zero evidence extracted," this skill successfully accesses structured data through direct HTTP calls to SIPRI's public file repository and embedded Datawrapper charts.

## Key Findings

### Data Access Patterns Discovered

1. **Direct Database Downloads**: SIPRI provides complete databases as downloadable XLSX files from their `/sites/default/files/` directory
2. **Datawrapper Charts**: Visualization data is served via Datawrapper CDN and accessible as CSV
3. **Publication PDFs**: Fact sheets and reports are downloadable with predictable URL patterns

### Available Databases

| Database | Coverage | Size | Update Frequency |
|----------|----------|------|------------------|
| Military Expenditure | 1949-2025 | ~900 KB | Annual (April) |
| Arms Industry Top 100 | 2002-2024 | ~260 KB | Annual (December) |
| Arms Industry Totals | 2002-2024 | ~19 KB | Annual (December) |

## Functions

### list_databases()

List all available databases and their details.

```python
result = await execute({"function": "list_databases"})
```

**Returns:**
```json
{
  "databases": [
    {
      "key": "milex_full",
      "description": "Complete Military Expenditure Database (1949-2025)",
      "format": "xlsx",
      "url": "https://www.sipri.org/sites/default/files/SIPRI-Milex-data-1949-2025_v1.2.xlsx"
    }
  ],
  "charts": [...]
}
```

### download_database(database: str)

Download and parse a complete database file.

```python
result = await execute({
    "function": "download_database",
    "database": "milex_full"
})
```

**Returns:**
```json
{
  "database": "milex_full",
  "description": "Complete Military Expenditure Database (1949-2025)",
  "size_bytes": 922529,
  "data": {
    "sheets": {
      "Sheet1": {
        "rows": [[...], [...]],
        "total_rows": 10000,
        "sample_rows": 1000
      }
    }
  }
}
```

**Available databases:**
- `milex_full`: Military Expenditure Database (1949-2025)
- `arms_industry_top100`: Top 100 Arms-Producing Companies
- `arms_industry_totals`: Total Arms Revenues Summary

### get_datawrapper_data(name: str | chart_id: str, version: str)

Extract data from embedded Datawrapper charts.

```python
# Using named chart
result = await execute({
    "function": "get_datawrapper_data",
    "name": "milex_gdp_share"
})

# Using chart ID directly
result = await execute({
    "function": "get_datawrapper_data",
    "chart_id": "g7sno",
    "version": "12"
})
```

**Returns:**
```json
{
  "chart_id": "g7sno",
  "version": "12",
  "rows": 193,
  "data": [
    {
      "Country": "Ukraine",
      "Share of GDP": "40.0%",
      "Country Code": "🇺🇦"
    },
    ...
  ]
}
```

**Available named charts:**
- `milex_gdp_share`: Military expenditure as share of GDP by country

### get_publication(url: str | year, type, title)

Retrieve publication metadata and download links.

```python
result = await execute({
    "function": "get_publication",
    "url": "/publications/2025/sipri-fact-sheets/trends-world-military-expenditure-2024"
})

# Or using components
result = await execute({
    "function": "get_publication",
    "year": "2025",
    "type": "sipri-fact-sheets",
    "title": "trends-world-military-expenditure-2024"
})
```

**Returns:**
```json
{
  "url": "https://www.sipri.org/publications/...",
  "title": "Trends in World Military Expenditure, 2024",
  "pdf_files": [
    {
      "url": "https://www.sipri.org/sites/default/files/2025-04/2504_fs_milex_2024.pdf",
      "filename": "2504_fs_milex_2024.pdf"
    }
  ],
  "datawrapper_charts": [...]
}
```

### search_publications(query: str, year: str)

Search for SIPRI publications.

```python
# Search by query
result = await execute({
    "function": "search_publications",
    "query": "military expenditure"
})

# Get all publications from a year
result = await execute({
    "function": "search_publications",
    "year": "2024"
})
```

**Returns:**
```json
{
  "query": "military expenditure",
  "publications": [
    {
      "url": "https://www.sipri.org/publications/2025/sipri-fact-sheets/...",
      "title": "Trends in World Military Expenditure 2024",
      "year": "2025"
    }
  ]
}
```

## Data Structure

### Military Expenditure Database

The XLSX file contains multiple sheets with:
- Country-level spending data (constant and current USD)
- Spending as percentage of GDP
- Year-over-year changes
- Regional aggregates
- Data from 1949 to 2025

### Arms Industry Database

Contains:
- Company rankings
- Arms sales revenues
- Total company revenues
- Country of origin
- Year-over-year changes

### Datawrapper Charts

Embedded charts provide quick-access data:
- Country comparisons
- Trend visualizations
- Regional breakdowns

## Technical Implementation

### Direct HTTP Access

Unlike browser automation, this skill uses direct HTTP requests:

```python
# Direct file download
url = "https://www.sipri.org/sites/default/files/SIPRI-Milex-data-1949-2025_v1.2.xlsx"
response = await session.get(url)

# Datawrapper CSV
csv_url = f"https://datawrapper.dwcdn.net/{chart_id}/{version}/dataset.csv"
```

### XLSX Parsing

Uses `openpyxl` to parse Excel files directly:

```python
workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
for sheet in workbook.sheetnames:
    for row in sheet.iter_rows():
        # Process row data
```

### URL Pattern Discovery

Key URL patterns discovered:
- Database files: `/sites/default/files/SIPRI-*.xlsx`
- Publication PDFs: `/sites/default/files/{year}-{month}/{filename}.pdf`
- Datawrapper: `https://datawrapper.dwcdn.net/{chart_id}/{version}/dataset.csv`

## Why Previous Probes Failed

The original probe report noted "23 opens with zero evidence extracted" because:

1. **JavaScript Rendering Assumption**: SIPRI pages don't require JS rendering for data access
2. **Overlooked Download Links**: Direct file download links are prominent but were missed
3. **Datawrapper Not Recognized**: Embedded charts weren't identified as data sources
4. **No API Expectation**: Searching for APIs when files are directly downloadable

## Usage Examples

### Example 1: Get Latest Military Spending Data

```python
# Download complete database
result = await execute({"function": "download_database", "database": "milex_full"})

# Parse 2024 spending
data = result["data"]["sheets"]["Constant USD"]["rows"]
header = data[0]
latest_year_idx = header.index("2024")

for row in data[1:]:
    country = row[0]
    spending_2024 = row[latest_year_idx]
    print(f"{country}: ${spending_2024:,.0f} million")
```

### Example 2: Get Top Spenders by GDP Share

```python
# Get Datawrapper chart data
result = await execute({"function": "get_datawrapper_data", "name": "milex_gdp_share"})

# Sort by GDP share
sorted_data = sorted(result["data"], key=lambda x: float(x["Share of GDP %"].rstrip('%')), reverse=True)

for country in sorted_data[:10]:
    print(f"{country['Country']}: {country['Share of GDP %']}")
```

### Example 3: Download Latest Fact Sheet

```python
# Search for latest milex fact sheet
result = await execute({
    "function": "search_publications",
    "query": "trends world military expenditure"
})

# Get the first result
pub = result["publications"][0]

# Get publication details
pub_details = await execute({
    "function": "get_publication",
    "url": pub["path"]
})

# Download PDF
pdf_url = pub_details["pdf_files"][0]["url"]
# ... download PDF
```

## Limitations

1. **Arms Transfers Database**: No direct file download available; requires web interface
2. **Peace Operations Database**: Similar limitation
3. **Chart Version Changes**: Datawrapper chart versions may change over time
4. **Embargoed Data**: Recent data may be embargoed before official release
5. **Large Files**: XLSX files >1MB may take longer to parse

## Rate Limiting

The skill implements conservative rate limiting:
- 2 requests per second
- 5 concurrent connections maximum
- 60-second timeout for large file downloads

## Data Freshness

- Military expenditure database updated annually in April
- Arms industry database updated annually in December
- Fact sheets published quarterly
- Datawrapper charts may be updated more frequently

## References

- SIPRI Databases: https://www.sipri.org/databases
- Military Expenditure: https://www.sipri.org/databases/milex
- Arms Industry: https://www.sipri.org/databases/armsindustry
- Datawrapper: https://datawrapper.dwcdn.net/