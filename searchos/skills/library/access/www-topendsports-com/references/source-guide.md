# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# TopEndSports Olympic Sports Access Skill

This skill fetches Olympic sports data from [TopEndSports](https://www.topendsports.com), a comprehensive sports reference website.

## Available Functions

### `get_sports_changes`

Fetches the complete history of Olympic sports changes, showing what sports were added or removed for each Olympic Games from 1896 to 2028.

**Returns:**
- `data`: Array of records with:
  - `year`: Olympic year (e.g., "2024", "2020")
  - `host`: Host city and country (e.g., "Paris, France")
  - `num_sports`: Number of sports in that Olympics
  - `change`: Description of changes (sports added/removed)

**Example:**
```json
{
  "function": "get_sports_changes"
}
```

### `get_sports_count`

Fetches a table showing the number of sports for each Olympic Games, including the Olympiad number.

**Returns:**
- `data`: Array of records with:
  - `olympiad`: Roman numeral (e.g., "XXXIII")
  - `year`: Olympic year
  - `host`: Host city and country
  - `num_sports`: Number of sports

**Example:**
```json
{
  "function": "get_sports_count"
}
```

### `get_discontinued`

Fetches a list of Olympic sports that have been discontinued.

**Returns:**
- `data`: Array of records with:
  - `name`: Sport name (e.g., "croquet", "polo", "tug-of-war")
  - `slug`: URL slug for the sport detail page
  - `url`: Full URL to the sport's page

**Example:**
```json
{
  "function": "get_discontinued"
}
```

### `get_sport_detail`

Fetches detailed information about a specific Olympic sport.

**Parameters:**
- `sport_slug` (required): The URL slug for the sport (e.g., "athletics", "swimming", "fencing")

**Returns:**
- `title`: Sport name/heading
- `description`: First paragraph description
- `content`: Array of content paragraphs
- `tables`: Any data tables on the page (if present)

**Example:**
```json
{
  "function": "get_sport_detail",
  "sport_slug": "athletics"
}
```

### `get_all_sports`

Fetches a list of all current Olympic summer sports with links to their detail pages.

**Returns:**
- `data`: Array of records with:
  - `name`: Sport name
  - `slug`: URL slug
  - `url`: Full URL to the sport's page

**Example:**
```json
{
  "function": "get_all_sports"
}
```

## Data Source

Data is sourced from TopEndSports' Olympic Games section:
- Sports changes: `/events/summer/sports/changes.htm`
- Sports count: `/events/summer/sports/number.htm`
- Discontinued sports: `/events/discontinued/index.htm`
- Individual sports: `/events/summer/sports/{slug}.htm`

## Notes

- The site uses simple HTML tables, making data extraction reliable
- Historical data covers Olympics from 1896 (Athens) to 2028 (Los Angeles)
- Sports changes data includes both added and removed sports for each Games
