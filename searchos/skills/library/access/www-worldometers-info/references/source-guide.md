# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Worldometers Country Statistics Access Skill

This skill extracts structured country statistics from [worldometers.info](https://www.worldometers.info), providing access to comprehensive demographic and geographic data.

## Available Functions

### 1. get_largest_countries

Retrieves a list of all countries ranked by total area.

**Parameters:**
- `limit` (optional, integer): Maximum number of countries to return

**Example:**
```json
{
  "function": "get_largest_countries",
  "limit": 10
}
```

**Returns:**
```json
{
  "success": true,
  "source": "https://www.worldometers.info/geography/largest-countries-in-the-world/",
  "total_countries": 10,
  "countries": [
    {
      "rank": 1,
      "country": "Russia",
      "total_area_km2": 17098242,
      "total_area_mi2": 6601665,
      "land_area_km2": 16376870,
      "land_area_mi2": 6323142,
      "world_share_percent": 11.0,
      "slug": "russia"
    }
  ]
}
```

### 2. get_population_by_country

Retrieves population statistics for all countries including growth rates, density, fertility rates, and more.

**Parameters:**
- `limit` (optional, integer): Maximum number of countries to return
- `country` (optional, string): Filter to countries matching this name (partial match)

**Example:**
```json
{
  "function": "get_population_by_country",
  "limit": 5
}
```

**Returns:**
```json
{
  "success": true,
  "source": "https://www.worldometers.info/world-population/population-by-country/",
  "total_countries": 5,
  "countries": [
    {
      "rank": 1,
      "country": "India",
      "population": 1476625576,
      "yearly_change_percent": 0.87,
      "net_change": 12760051,
      "density_per_km2": 497,
      "land_area_km2": 2973190,
      "migrants_net": -440456,
      "fertility_rate": 1.93,
      "median_age": 29.2,
      "urban_population_percent": 37.6,
      "world_share_percent": 17.79,
      "slug": "india"
    }
  ]
}
```

### 3. get_country_population_details

Retrieves detailed population history and projections for a specific country, including urban area breakdowns.

**Parameters:**
- `country` (required, string): Country name or slug (e.g., "India", "india", "United States")

**Example:**
```json
{
  "function": "get_country_population_details",
  "country": "india"
}
```

**Returns:**
```json
{
  "success": true,
  "source": "https://www.worldometers.info/world-population/india-population/",
  "country": "india",
  "slug": "india",
  "title": "India Population (2026) - Worldometer",
  "population_history": [
    {
      "Year": 2024,
      "Population": 1463855531,
      "Yearly % Change": 0.92,
      "Yearly Change": 13330797,
      "Migrants (net)": -453926,
      "Median Age": 28.8,
      "Fertility Rate": 1.96,
      "Density (P/Km²)": 492,
      "Urban Pop %": 36.6,
      "Urban Population": 535862647,
      "Country's Share of World Pop": 17.76,
      "World Population": 8237844750,
      "India Global Rank": 1
    }
  ],
  "population_forecasts": [
    {
      "Year": 2030,
      "Population": 1525138844,
      "Yearly % Change": 0.82,
      "Yearly Change": 12254664,
      "Migrants (net)": -388547,
      "Median Age": 30.8,
      "Fertility Rate": 1.88,
      "Density (P/Km²)": 513,
      "Urban Pop %": 39.8,
      "Urban Population": 607341981,
      "Country's Share of World Pop": 17.8,
      "World Population": 8569124911,
      "India Global Rank": 1
    }
  ],
  "urban_areas": [
    {
      "rank": 1,
      "urban_area": "Delhi",
      "population": 33807403
    }
  ]
}
```

## Data Notes

- All population figures are integers
- Percentages are returned as floats (e.g., 11.0 means 11%)
- Negative values for migrants indicate net emigration
- The `slug` field can be used to query specific country details
- Data is sourced from Worldometers real-time statistics

## Error Handling

Functions return an `error` field with a descriptive message when:
- Required parameters are missing
- The country is not found (for `get_country_population_details`)
- Network or parsing errors occur
