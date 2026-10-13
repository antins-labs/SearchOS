# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# The World Factbook - Country Profile Access

This skill extracts structured country data from [The World Factbook](https://theworldfactbook.org), a comprehensive resource published by the CIA providing detailed information on the history, people, government, economy, energy, geography, communications, transportation, military, and transnational issues for world entities.

## Features

- **Full Country Profiles**: Retrieve complete structured data for any country
- **Section Filtering**: Query specific sections like Geography, Economy, Government
- **Key Search**: Find specific data points by keyword across all sections
- **Quick Summary**: Get essential facts about a country in one call

## Data Structure

Each country profile is organized into these sections:

- **Overview**: Capital, Population, Area, Location
- **Background**: Historical context and introduction
- **Geography**: Location, coordinates, area, boundaries, climate, terrain
- **People and Society**: Population, age structure, ethnic groups, languages, religions
- **Environment**: Environmental issues, agreements, land use, natural hazards
- **Government**: Government type, capital, administrative divisions, legal system
- **Economy**: GDP, inflation, unemployment, industries, trade
- **Energy**: Electricity, oil, natural gas, renewable energy
- **Communications**: Telephones, internet, broadcast media
- **Transportation**: Airports, railways, roadways, ports
- **Military and Security**: Military forces, expenditures, service age
- **Space**: Space agency, launch sites, program overview
- **Terrorism**: Terrorist groups
- **Transnational Issues**: Refugees, disputes, illicit drugs

## Usage Examples

### Get Full Country Profile

```json
{
  "function": "get_profile",
  "country": "iran"
}
```

Returns all available data organized by section.

### Get Specific Section

```json
{
  "function": "get_profile",
  "country": "mexico",
  "section": "economy"
}
```

Returns only the Economy section data.

### Filter by Keys

```json
{
  "function": "get_profile",
  "country": "japan",
  "keys": ["population", "gdp", "area"]
}
```

Returns data items containing "population", "gdp", or "area" in their keys.

### Search for Specific Data

```json
{
  "function": "search_key",
  "country": "germany",
  "search_term": "exports"
}
```

Returns all data items with "exports" in the key name.

### List Available Sections

```json
{
  "function": "list_sections",
  "country": "france"
}
```

Returns a list of all sections with item counts.

### Get Quick Summary

```json
{
  "function": "get_summary",
  "country": "brazil"
}
```

Returns essential facts: capital, population, area, government type, GDP, and background.

## Country Name Format

The `country` parameter accepts:
- Common names: `iran`, `mexico`, `japan`
- Official names: `united-states`, `united-kingdom`, `south-korea`
- Names with spaces should use hyphens: `south-africa`, `new-zealand`

## Data Notes

- All monetary values are typically in US dollars
- Population figures include year estimates (e.g., "2024 est.")
- Some data items contain multiple years for comparison
- Text descriptions may be truncated for very long entries

## Technical Details

The World Factbook uses a consistent page template with:
- Key-value pairs in `<article class="feed-item--kv">` elements
- Sections marked by `<article class="country-section-head">` headers
- Data organized in a single `<div class="panel">` container

This skill parses the HTML directly without requiring JavaScript rendering, ensuring fast and reliable data extraction.
