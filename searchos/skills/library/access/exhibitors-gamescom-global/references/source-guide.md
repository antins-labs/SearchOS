# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Gamescom Exhibitor Search

This skill retrieves exhibitor information from the official Gamescom exhibitor database at [exhibitors.gamescom.global](https://exhibitors.gamescom.global).

## Features

- **Search exhibitors** by name, brand, product, or country
- **Filter results** by country, hall, product sector, or company initial
- **Get detailed information** about specific exhibitors including address, website, and product groups
- **Browse available filters** for countries, halls, and product sectors

## Functions

### search

Search for exhibitors with optional filters.

**Parameters:**
- `query` (optional): Search term for exhibitor name, brand, product, or country
- `country` (optional): Filter by country/region (e.g., "Germany", "Japan", "USA")
- `hall` (optional): Filter by hall number (e.g., "Hall 10.1", "Hall 9.1")
- `product_sector` (optional): Filter by product sector (e.g., "entertainment area", "indie area")
- `initial` (optional): Filter by first letter of company name (A-Z)
- `search_type` (optional): "alle" (all words), "any" (any word), "exact" (exact phrase), "title" (only in title)
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Results per page (default: 20)

**Returns:**
- List of exhibitors with name, country, hall, stand, and link
- Pagination information

### get_exhibitor

Get detailed information about a specific exhibitor.

**Parameters:**
- `slug` (required): Exhibitor identifier from search results (e.g., "nintendo", "_outlook_2")

**Returns:**
- Company name and address
- Website URL
- Logo URL
- Product groups, brands, product sectors, target markets

### get_filters

Get available filter options for searching.

**Returns:**
- List of available countries
- List of available halls
- List of product sectors
- List of target markets
- List of initials (A-Z)

## Example Usage

### Search for exhibitors
```json
{
  "function": "search",
  "query": "nintendo"
}
```

### Filter by country
```json
{
  "function": "search",
  "country": "Japan",
  "page": 1
}
```

### Filter by hall
```json
{
  "function": "search",
  "hall": "Hall 10.1"
}
```

### Get exhibitor details
```json
{
  "function": "get_exhibitor",
  "slug": "nintendo"
}
```

### Get available filters
```json
{
  "function": "get_filters"
}
```

## Data Source

All data is retrieved from the official Gamescom exhibitor portal. The data includes:
- Exhibitor names and contact information
- Hall and stand locations
- Country of origin
- Product groups and brands
- Target markets

## Notes

- The exhibitor database is for the upcoming Gamescom event (currently 2026)
- Some contact details may require login to view
- Results are paginated (typically 20 per page)
- Hall numbering follows the Gamescom venue layout
