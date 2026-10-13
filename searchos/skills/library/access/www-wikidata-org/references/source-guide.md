# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Wikidata Access Skill

This skill provides structured access to Wikidata, the free knowledge base that anyone can edit. It extracts entity data including labels, descriptions, claims (properties), and sitelinks.

## Features

### Get Item by ID
Fetch detailed information about a specific Wikidata entity by its ID.

**Example:**
```json
{
  "function": "get_item",
  "item_id": "Q926972"
}
```

**With filters:**
```json
{
  "function": "get_item",
  "item_id": "Q926972",
  "properties": ["P31", "P106", "P569", "P570"],
  "language": "en"
}
```

**Returns:**
- `id`: Wikidata entity ID
- `label`: Entity label in the specified language
- `description`: Entity description
- `aliases`: List of alternative names
- `claims`: Dictionary of property claims with values
- `sitelinks`: Links to Wikipedia and other Wikimedia projects

### Search Items
Search for Wikidata entities by keyword.

**Example:**
```json
{
  "function": "search_items",
  "query": "Michael Scott Apple",
  "limit": 10
}
```

**Returns:**
- `results`: List of matching entities with IDs, labels, and descriptions
- `total`: Number of results returned

## Common Property IDs

| Property | ID | Description |
|----------|-----|-------------|
| Instance of | P31 | Type of entity |
| Sex or gender | P21 | Gender |
| Country of citizenship | P27 | Nationality |
| Given name | P735 | First name |
| Family name | P734 | Last name |
| Date of birth | P569 | Birth date |
| Date of death | P570 | Death date |
| Occupation | P106 | Profession |
| Employer | P108 | Organization |

## Use Cases

1. **Entity Resolution**: Get structured data about people, places, organizations, concepts
2. **Knowledge Extraction**: Extract facts and relationships from Wikidata's knowledge graph
3. **Cross-Reference**: Access sitelinks to Wikipedia articles across languages
4. **Data Enrichment**: Add Wikidata IDs and properties to your datasets

## Notes

- Item IDs can be provided with or without the "Q" prefix
- Property IDs can be provided with or without the "Property:" prefix
- The skill uses browser automation to handle Wikidata's JavaScript-rendered pages
- Results include both property IDs and human-readable labels for convenience
