# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# A Wiki of Ice and Fire Access Skill

This skill extracts structured data from [A Wiki of Ice and Fire](https://awoiaf.westeros.org), the comprehensive encyclopedia for George R.R. Martin's *A Song of Ice and Fire* series and the HBO adaptation *Game of Thrones*.

## Features

- **Character Infobox Extraction**: Retrieves detailed attributes including:
  - Titles and aliases
  - Birth/death dates and locations
  - Family relationships (parents, spouses, children, siblings)
  - Allegiances and culture
  - Book appearances and TV series information

- **Biographical Content**: Extracts introductory paragraphs and section structure

- **Category Information**: Lists all wiki categories the character belongs to

## Functions

### get_character

Retrieve complete information about a specific character.

**Parameters:**
- `name` (required): The character's name as it appears in the wiki (e.g., "Eddard Stark", "Daenerys Targaryen")

**Returns:**
```json
{
  "name": "Robb Stark",
  "url": "https://awoiaf.westeros.org/index.php/Robb_Stark",
  "infobox": {
    "title": "King Robb Stark the Young Wolf",
    "sections": {
      "Monarch": {
        "Reign": {"value": "299 AC", "links": [...]},
        "Titles": {"value": "Lord of Winterfell, King in the North", "links": [...]}
      },
      "Personal Information": {
        "Born": {"value": "283 AC, Riverrun", "links": [...]},
        "Died": {"value": "299 AC (aged 16), The Twins", "links": [...]}
      },
      "Family": {
        "Father": {"value": "Lord Eddard Stark", "links": [...]},
        "Mother": {"value": "Lady Catelyn Tully", "links": [...]}
      }
    },
    "fields": {"Reign": "299 AC", "Born": "283 AC Riverrun", ...}
  },
  "intro": "Robb Stark is the eldest son of Lord Eddard Stark...",
  "sections": [{"title": "Appearance and Character"}, {"title": "History"}, ...],
  "categories": ["House Stark", "283 AC births", "299 AC deaths", ...]
}
```

### search_characters

Attempt to find a character page matching the query. Since direct search is disabled on this wiki, this function tries direct URL navigation and provides suggestions.

**Parameters:**
- `query` (required): Search term or character name

**Returns:**
- If found: Full character data (same as get_character)
- If not found: Suggestions and list of popular characters

## Usage Examples

### Get a character's information
```json
{
  "function": "get_character",
  "name": "Tyrion Lannister"
}
```

### Search for a character
```json
{
  "function": "search_characters",
  "query": "Jon Snow"
}
```

## Notes

- The wiki uses standard MediaWiki formatting with infobox tables containing character attributes
- Character names should match the wiki's naming convention (typically full names with proper capitalization)
- The infobox parser handles section headers and extracts both text values and linked entities
- All URLs are absolute and point to the awoiaf.westeros.org domain
