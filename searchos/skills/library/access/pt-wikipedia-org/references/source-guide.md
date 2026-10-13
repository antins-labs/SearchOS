# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Portuguese Wikipedia Access Skill

This skill extracts structured data from Portuguese Wikipedia (pt.wikipedia.org), specifically designed to handle the high-value tables and infoboxes that may fail to render through generic readers.

## Features

### 1. Get Page Content (`get_page`)
Retrieves general article content and metadata:
- Article title and URL
- First 10 paragraphs of content
- Section headings
- Presence of infobox and count of wikitables
- Page categories
- Last modified date

**Example:**
```python
execute({
    "function": "get_page",
    "title": "São Paulo"
})
```

### 2. Extract Infobox (`extract_infobox`)
Extracts structured data from Wikipedia infoboxes (the summary tables on the right side of articles). Particularly useful for:
- Municipality pages (Municípios)
- City information
- Geographic entities
- Biographical articles

Returns:
- Article title
- Infobox type (e.g., "Município do Brasil")
- Structured key-value pairs
- Coordinates (when available)

**Example:**
```python
execute({
    "function": "extract_infobox",
    "url": "https://pt.wikipedia.org/wiki/Palmelo"
})
```

**Sample output for Palmelo:**
```json
{
    "title": "Palmelo",
    "type": "Município do Brasil",
    "data": {
        "Lema": "Dar aos outros o que de graça receber",
        "Gentílico": "palmario",
        "País": "Brasil",
        "Unidade federativa": "Goiás",
        "Municípios limítrofes": "Santa Cruz de Goiás e Pires do Rio",
        "Distância até a capital": "130 km",
        "Fundação": "13 de novembro de 1953 (72 anos)",
        "Área Total": "58,997 km²",
        "População Total": "2 380 hab.",
        "Densidade": "40,3 hab./km²",
        "IDH": "0,787 — alto"
    }
}
```

### 3. Extract Table (`extract_table`)
Extracts data from wikitable tables, such as:
- Lists of municipalities
- Statistical rankings
- Comparison tables
- Data tables

**Parameters:**
- `url` or `title`: Page containing the table
- `table_index`: Index of table to extract (default: 0)
- `max_rows`: Maximum rows to return (default: all)

**Example:**
```python
execute({
    "function": "extract_table",
    "title": "Lista de municípios de Goiás por área",
    "max_rows": 10
})
```

**Sample output:**
```json
{
    "title": "Lista de municípios de Goiás por área",
    "headers": ["Posição", "Município", "Área (km²)", "% do estado"],
    "rows": [
        {"Posição": "1", "Município": "Niquelândia", "Área (km²)": "9 843,247", "% do estado": "2,8933"},
        {"Posição": "2", "Município": "Mineiros", "Área (km²)": "9 038,775", "% do estado": "2,6569"},
        ...
    ],
    "row_count": 10
}
```

## Data Cleaning

The skill automatically:
- Removes Wikipedia reference markers like [1], [2]
- Converts non-breaking spaces (\xa0) to regular spaces
- Normalizes whitespace
- Skips image-related fields (flags, coats of arms)

## Use Cases

1. **Municipal Data Extraction**: Extract population, area, founding dates, and other statistics for Brazilian municipalities
2. **Geographic Lists**: Parse ranked lists of cities/states by various metrics
3. **Statistical Tables**: Extract structured data from comparison tables
4. **General Article Reading**: Get clean content from Portuguese Wikipedia pages

## Technical Notes

- Uses Playwright browser automation to handle JavaScript-rendered content
- Includes proper Portuguese locale settings
- Handles page load timeouts gracefully
- Works with both full URLs and article titles

## Error Handling

Returns structured error messages for:
- Missing required parameters
- Pages without infoboxes/tables
- Network or loading failures
- Invalid table indices
