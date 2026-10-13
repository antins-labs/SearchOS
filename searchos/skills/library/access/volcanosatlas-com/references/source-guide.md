# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# VolcanoAtlas Access Skill

Fetches volcano data from [volcanosatlas.com](https://volcanosatlas.com), a comprehensive database of volcanoes worldwide.

## Features

### List Countries
Get a list of all countries with volcanoes, including volcano counts.

```
function: list_countries
```

Returns:
- List of countries with volcano counts
- Country names, slugs, and URLs

### Get Country Volcanoes
Get all volcanoes for a specific country with summary statistics.

```
function: get_country_volcanoes
country: Chile
```

Returns:
- Country statistics (total volcanoes, historically active count)
- List of volcanoes with details (name, elevation, type, last eruption, evidence, VEI max)
- Volcano URLs for further details

### Get Volcano Detail
Get detailed information about a specific volcano.

```
function: get_volcano_detail
slug: villarrica
```

Returns:
- Name and elevation
- Type (stratovolcano, shield, etc.)
- Coordinates (latitude, longitude)
- Last eruption year
- VEI max (Volcanic Explosivity Index)
- Risk assessments (population, infrastructure, aviation)
- Country

## Data Notes

- **Chile data**: The site has complete volcano data for Chile (90 volcanoes) with full details in the table.
- **Argentina data**: The Argentina page table has rendering issues (shows "Unknown" values), but volcano links are available. The skill falls back to extracting volcano names from links.
- **Volcano slugs**: Use the slug from the URL (e.g., `villarrica` from `/volcano/villarrica`).

## Example Usage

```python
# List all countries
result = await execute({'function': 'list_countries'}, ctx)

# Get Chile's volcanoes
result = await execute({'function': 'get_country_volcanoes', 'country': 'Chile'}, ctx)

# Get details for Villarrica volcano
result = await execute({'function': 'get_volcano_detail', 'slug': 'villarrica'}, ctx)
```

## Response Format

All responses include a `success` field indicating whether the request succeeded. On error, an `error` field contains the error message.

Successful responses include:
- `success`: true
- Requested data (countries, volcanoes, or volcano details)
- `total_count`: Number of items returned (for lists)
- `url`: Source URL for the data
