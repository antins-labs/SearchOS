# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Theodora.com World Factbook Access Skill

This skill extracts structured country geography data from theodora.com's CIA World Factbook pages.

## Features

- **get_geography**: Retrieve comprehensive geography data for a country by name
- **get_geography_by_url**: Fetch geography data from a specific theodora.com URL
- **list_countries**: Get a list of all available countries
- **list_sections**: Discover all available data sections for a specific country

## Data Fields Extracted

For each country, the following geography fields are extracted (when available):

- Location
- Geographic coordinates
- Map references
- Area (total, land, water)
- Area - comparative
- Land boundaries (with border countries)
- Coastline
- Maritime claims
- Climate
- Terrain
- Elevation (highest/lowest points)
- Natural resources
- Land use
- Irrigated land
- Major lakes
- Major rivers
- Major watersheds
- Major aquifers
- Population distribution
- Natural hazards
- Geography - note

## Usage Examples

### Get geography data for Russia
```json
{
  "function": "get_geography",
  "country": "russia"
}
```

### Get geography data for China
```json
{
  "function": "get_geography",
  "country": "china"
}
```

### Get geography from a specific URL
```json
{
  "function": "get_geography_by_url",
  "url": "https://theodora.com/wfbcurrent/china/china_geography.html"
}
```

### List all available countries
```json
{
  "function": "list_countries"
}
```

### List available sections for a country
```json
{
  "function": "list_sections",
  "country": "russia"
}
```

## URL Patterns

The skill supports both URL patterns used by theodora.com:
- `https://theodora.com/world_fact_book_2024/{country}/{country}_geography.html`
- `https://theodora.com/wfbcurrent/{country}/{country}_geography.html`

## Country Name Format

Country names should be provided in lowercase with underscores or spaces:
- `russia` or `Russia`
- `united_states` or `united states`
- `china` or `China`

## Return Format

The `get_geography` function returns a structured object:

```json
{
  "country": "Russia",
  "url": "https://theodora.com/world_fact_book_2024/russia/russia_geography.html",
  "fields": {
    "Location": "North Asia bordering the Arctic Ocean...",
    "Geographic coordinates": "60 00 N, 100 00 E",
    "Area": "total:\n17,098,242 sq km\nland:\n16,377,742 sq km...",
    ...
  }
}
```

## Notes

- The site uses a simple HTML structure with `<h3>` headers for field names and `<p>` paragraphs for values
- Some fields contain multi-line data (e.g., Area with total/land/water breakdowns)
- The skill automatically tries both URL patterns (2024 and current) to maximize coverage
