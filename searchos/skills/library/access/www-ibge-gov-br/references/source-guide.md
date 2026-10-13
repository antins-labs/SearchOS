# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# IBGE Municipality Statistics Access Skill

This skill retrieves official Brazilian municipality statistics from IBGE (Instituto Brasileiro de Geografia e Estatística) using their public API at `servicodados.ibge.gov.br`.

## Overview

The IBGE website (www.ibge.gov.br) is protected by Cloudflare, making direct scraping unreliable. This skill bypasses that limitation by using IBGE's public API endpoints directly, which provides structured JSON data without requiring browser automation.

## Available Functions

### 1. search_municipalities
Search for municipalities by name (case-insensitive partial match).

**Parameters:**
- `query` (string, required): Municipality name or partial name to search

**Example:**
```json
{
  "function": "search_municipalities",
  "query": "palmelo"
}
```

**Returns:** List of matching municipalities with ID, name, state, and region.

### 2. get_municipality
Get detailed location information for a specific municipality.

**Parameters:**
- `municipality_id` (integer, required): 7-digit IBGE municipality code

**Example:**
```json
{
  "function": "get_municipality",
  "municipality_id": 5215801
}
```

**Returns:** Municipality details including microregion, mesoregion, state, and geographic regions.

### 3. get_municipality_statistics
Get statistical indicators for a municipality from the Sinopse Municipal survey.

**Parameters:**
- `municipality_id` (integer, required): 7-digit IBGE municipality code

**Example:**
```json
{
  "function": "get_municipality_statistics",
  "municipality_id": 5215801
}
```

**Returns:** Statistics including:
- População estimada (Estimated population)
- População (Census population)
- Área da unidade territorial (Area in km²)
- Densidade demográfica (Population density)
- Prefeito (Mayor)
- Gentílico (Demonym)
- Bioma Predominante (Predominant biome)
- And more regional/geographic codes

### 4. get_municipality_full
Get complete municipality data including both location details and statistics.

**Parameters:**
- `municipality_id` (integer, required): 7-digit IBGE municipality code

**Example:**
```json
{
  "function": "get_municipality_full",
  "municipality_id": 5215801
}
```

### 5. get_state_municipalities
Get all municipalities in a Brazilian state.

**Parameters:**
- `state` (string, required): Brazilian state abbreviation (e.g., GO, SP, RJ)

**Example:**
```json
{
  "function": "get_state_municipalities",
  "state": "GO"
}
```

### 6. get_states
Get all 27 Brazilian states (26 states + Federal District).

**Example:**
```json
{
  "function": "get_states"
}
```

## Data Sources

The skill retrieves data from:
- **Localidades API**: Geographic and administrative data (states, municipalities, regions)
- **Pesquisas API (Survey 33 - Sinopse Municipal)**: Statistical indicators including population, area, density, mayor, and geographic classifications

## Finding Municipality IDs

To find a municipality's ID:
1. Use `search_municipalities` with the municipality name
2. Use `get_state_municipalities` to list all municipalities in a state

## Example: Complete Workflow

```json
// 1. Search for a municipality
{"function": "search_municipalities", "query": "rio de janeiro"}

// 2. Get full data using the ID from search results
{"function": "get_municipality_full", "municipality_id": 3304557}
```

## Notes

- All API endpoints are public and require no authentication
- The Sinopse Municipal survey provides the most comprehensive basic statistics
- Population data includes both census years and annual estimates
- Some indicators may not have data for all municipalities
- The API returns data in Portuguese as per IBGE conventions
