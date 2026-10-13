# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Farmonaut Mining Data Skill

Extracts mineral reserves data tables from farmonaut.com mining pages.

## Overview

Farmonaut hosts USGS Mineral Commodity Summaries data with detailed country-level reserves information. This skill extracts structured table data from these pages.

## Functions

### get_mineral_reserves

Extracts the main mineral reserves table from a farmonaut mining URL.

**Parameters:**
- `url` (required): Full URL to the farmonaut mining page

**Returns:**
- `url`: The source URL
- `title`: Page title
- `headers`: Column headers from the table
- `row_count`: Number of data rows
- `data`: List of records (each row as a dict keyed by column headers)

**Example:**
```python
result = await execute({
    "function": "get_mineral_reserves",
    "url": "https://farmonaut.com/mining/usgs-mineral-commodity-summaries-rare-earths-reserves-by-country"
}, ctx)
```

**Sample Output:**
```json
{
  "url": "https://farmonaut.com/mining/usgs-mineral-commodity-summaries-rare-earths-reserves-by-country",
  "title": "USGS Mineral Commodity Summaries: Rare Earths Reserves By Country",
  "headers": ["Country", "Estimated Rare Earths Reserves (thousand metric tons)", "Global Share (%)", ...],
  "row_count": 9,
  "data": [
    {"Country": "China", "Estimated Rare Earths Reserves (thousand metric tons)": "44,000", "Global Share (%)": "33–38%", ...},
    {"Country": "Vietnam", "Estimated Rare Earths Reserves (thousand metric tons)": "22,000", "Global Share (%)": "~17%", ...}
  ]
}
```

### get_all_tables

Extracts all tables from a farmonaut page.

**Parameters:**
- `url` (required): Full URL to the farmonaut page

**Returns:**
- `url`: The source URL
- `title`: Page title
- `table_count`: Number of tables found
- `tables`: List of table objects, each with headers, row_count, and data

## Known Working URLs

- `https://farmonaut.com/mining/usgs-mineral-commodity-summaries-rare-earths-reserves-by-country` - Rare Earths reserves by country

## Data Columns

Typical columns in the reserves tables:
- Country
- Estimated Reserves (with units)
- Global Share (%)
- Main Applications in Agriculture/Forestry
- Supply Risk Level
- Relevance to Advanced Technology Adoption

## Error Handling

Returns an `error` key in the response dict when:
- URL is invalid or unreachable
- HTTP request fails or times out
- No tables are found on the page
- Page returns non-200 status
