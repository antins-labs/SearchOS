# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Clash Royale Fandom Wiki Access Skill

This skill retrieves structured card statistics from the Clash Royale Fandom wiki (clashroyale.fandom.com).

## Overview

The skill uses the Fandom MediaWiki API to extract:
- **Infobox data**: Card name, elixir cost, rarity, type, arena unlock, release date
- **Attribute tables**: Hit speed, speed, range, deploy time, target type, etc.
- **Level statistics**: Hitpoints, damage, and other stats at each level

## Functions

### get_card

Retrieves detailed information about a specific card.

**Parameters:**
- `card_name` (required): The card name, with spaces or underscores (e.g., 'Mega_Knight', 'P.E.K.K.A.')

**Returns:**
```json
{
  "success": true,
  "card_name": "Mega Knight",
  "url": "https://clashroyale.fandom.com/wiki/Mega_Knight",
  "infobox": {
    "name": "Mega Knight",
    "image": "https://...",
    "cost": {"label": "Elixir Cost", "value": "7"},
    "rarity": {"label": "Rarity", "value": "Legendary"},
    ...
  },
  "attributes": {
    "cost": {"label": "Cost", "value": "7"},
    "hit_speed": {"label": "Hit Speed", "value": "1.7 sec"},
    ...
  },
  "level_stats": [
    {"level": "9", "hitpoints": "3300", "area_damage": "221", ...},
    {"level": "10", "hitpoints": "3630", "area_damage": "243", ...},
    ...
  ],
  "sections": ["Modifiers", "Strategy", "Statistics", ...]
}
```

### search_cards

Searches for cards matching a query.

**Parameters:**
- `query` (required): Search term (e.g., 'knight', 'goblin', 'legendary')

**Returns:**
```json
{
  "success": true,
  "query": "knight",
  "total": 10,
  "results": [
    {
      "title": "Knight",
      "page_id": 250,
      "url": "https://clashroyale.fandom.com/wiki/Knight",
      "snippet": "...",
      "size": 12345,
      "wordcount": 1500
    },
    ...
  ]
}
```

### list_cards

Lists all cards in a specific category.

**Parameters:**
- `category` (optional): Card category (default: 'Troop_Cards')
  - Valid values: 'Troop_Cards', 'Spell_Cards', 'Building_Cards', 
    'Legendary_Cards', 'Epic_Cards', 'Rare_Cards', 'Common_Cards', 'Champion_Cards'
- `limit` (optional): Maximum results (default: 50, max: 500)

**Returns:**
```json
{
  "success": true,
  "category": "Troop_Cards",
  "total": 85,
  "cards": [
    {
      "name": "Knight",
      "page_id": 250,
      "url": "https://clashroyale.fandom.com/wiki/Knight"
    },
    ...
  ]
}
```

## Examples

### Get Mega Knight stats
```json
{
  "function": "get_card",
  "card_name": "Mega_Knight"
}
```

### Search for goblin cards
```json
{
  "function": "search_cards",
  "query": "goblin"
}
```

### List all spell cards
```json
{
  "function": "list_cards",
  "category": "Spell_Cards",
  "limit": 100
}
```

## Notes

- The skill uses the Fandom MediaWiki API which is publicly accessible
- Card names are case-insensitive and support both spaces and underscores
- Some cards may have redirects (e.g., 'P.E.K.K.A' redirects to 'P.E.K.K.A.')
- Level statistics may vary in structure depending on the card type
