# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# IBGE Municipal Data Access Skill

This skill retrieves structured municipal data from IBGE (Instituto Brasileiro de Geografia e Estatística) - the Brazilian Institute of Geography and Statistics.

## Overview

The skill uses IBGE's official public APIs to fetch comprehensive data about Brazilian municipalities, including:

- **Geographic hierarchy**: State, region, microregion, mesoregion, immediate/intermediate regions
- **Population data**: Resident population from Censo 2022
- **Area data**: Territorial area in km²
- **Density**: Demographic density (inhabitants/km²)
- **Economic data**: GDP (Produto Interno Bruto) at current prices
- **Administrative divisions**: Districts within each municipality

## Functions

### get_municipality
Get municipality details by state abbreviation and name.

**Parameters:**
- `state`: Brazilian state abbreviation (e.g., "GO", "SP", "RJ")
- `name`: Municipality name (e.g., "Palmelo", "São Paulo")

**Example:**
```json
{
  "function": "get_municipality",
  "state": "GO",
  "name": "Palmelo"
}
```

### get_by_id
Get municipality details by IBGE ID.

**Parameters:**
- `municipality_id`: 7-digit IBGE municipality ID (e.g., 5215801)

**Example:**
```json
{
  "function": "get_by_id",
  "municipality_id": 5215801
}
```

### get_districts
Get list of districts within a municipality.

**Parameters:**
- `municipality_id`: IBGE municipality ID

**Example:**
```json
{
  "function": "get_districts",
  "municipality_id": 5215801
}
```

### get_population_area
Get population and area data from Censo 2022.

**Parameters:**
- `municipality_id`: IBGE municipality ID

**Returns:**
- População residente (resident population)
- Área da unidade territorial (territorial area)
- Densidade demográfica (demographic density)

**Example:**
```json
{
  "function": "get_population_area",
  "municipality_id": 5215801
}
```

### get_gdp
Get GDP (Produto Interno Bruto) data.

**Parameters:**
- `municipality_id`: IBGE municipality ID
- `periods`: Period specification (optional, default: "-1" for latest)
  - "-1": Latest year only
  - "-5": Last 5 years
  - "all": All available years

**Example:**
```json
{
  "function": "get_gdp",
  "municipality_id": 5215801,
  "periods": "-5"
}
```

### get_stats
Get comprehensive statistics for a municipality (population, area, GDP, districts).

**Parameters:**
- `municipality_id`: IBGE municipality ID, OR
- `state` + `name`: State abbreviation and municipality name

**Example:**
```json
{
  "function": "get_stats",
  "municipality_id": 5215801
}
```

### list_states
List all Brazilian states.

**Example:**
```json
{
  "function": "list_states"
}
```

### list_municipalities
List all municipalities in a state.

**Parameters:**
- `state`: Brazilian state abbreviation

**Example:**
```json
{
  "function": "list_municipalities",
  "state": "GO"
}
```

## Data Sources

All data comes from IBGE's official APIs:
- **Localidades API**: Geographic hierarchy and municipality identification
- **Agregados API**: Statistical data (population, area, GDP)

## Notes

- The IBGE cidades.ibge.gov.br website is a JavaScript SPA that cannot be easily scraped
- This skill uses the underlying public APIs that power the website
- Data is available in Portuguese as per IBGE's official terminology
- Population data is from Censo 2022 (Brazilian Census)
- GDP data is updated annually (latest available: 2023)

## Common Use Cases

1. **Find municipality information**: Use `get_municipality` with state and name
2. **Get population statistics**: Use `get_population_area` with municipality ID
3. **Economic analysis**: Use `get_gdp` with municipality ID
4. **Comprehensive overview**: Use `get_stats` for all available data
5. **Browse locations**: Use `list_states` and `list_municipalities` to discover available entities
