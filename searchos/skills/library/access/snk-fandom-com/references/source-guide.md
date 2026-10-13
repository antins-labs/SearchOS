# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# SNK Fandom Wiki Access Skill

Extracts structured character information from the SNK Fandom Wiki (snk.fandom.com), bypassing Cloudflare protection by using the MediaWiki API directly.

## Functions

### get_character
Get detailed information about a SNK character.

**Parameters:**
- `page` (required): Character page name (e.g., "Krizalid", "Omega_Rugal", "Clone_Zero")
- `include_sections` (optional, default: true): Include full section content

**Returns:**
- `title`: Character display name
- `infobox`: Structured character data (name, image, stats, biography)
- `sections`: List of available sections
- `content_sections`: Full content of each section
- `introduction`: First paragraph summary

**Example infobox fields:**
- Full Name, Birthdate, Birthplace, Height, Weight
- Blood Type, Family/Relatives, Job/Occupation
- Likes, Dislikes, Hobbies, Favorite Food
- Weapon, Fighting Style

### search_characters
Search for characters by name.

**Parameters:**
- `query` (required): Search term
- `limit` (optional, default: 10, max: 50): Maximum results

**Returns:**
- List of matching pages with title, description, URL, and page name

### list_characters
List characters from a category.

**Parameters:**
- `category` (optional, default: "Characters"): Category name
- `limit` (optional, default: 20, max: 500): Maximum results
- `offset` (optional): Pagination token from previous query

**Returns:**
- List of character names and page IDs
- `continue` token for pagination if more results available

### get_section
Get a specific section from a character page.

**Parameters:**
- `page` (required): Character page name
- `section` (required): Section name (case-insensitive) or numeric index

**Returns:**
- Section name, index, and full text content

## Usage Examples

### Get character info
```json
{
  "function": "get_character",
  "page": "Krizalid"
}
```

### Search for characters
```json
{
  "function": "search_characters",
  "query": "Rugal"
}
```

### List all characters
```json
{
  "function": "list_characters",
  "limit": 50
}
```

### Get specific section
```json
{
  "function": "get_section",
  "page": "Omega_Rugal",
  "section": "Powers"
}
```

## Notes

- Uses the MediaWiki API endpoint directly to bypass Cloudflare protection
- Character pages include portable infoboxes with standardized data fields
- The wiki covers characters from The King of Fighters, Samurai Shodown, Metal Slug, and other SNK games
- Page names use underscores for spaces (e.g., "Omega_Rugal")
