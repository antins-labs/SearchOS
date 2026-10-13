# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Mascots Fandom Wiki Access Skill

This skill provides access to the [Mascots Fandom Wiki](https://mascots.fandom.com), a comprehensive wiki dedicated to documenting mascots from sporting events, brands, organizations, and more.

## Features

### Get Mascot Details
Retrieve detailed information about a specific mascot including:
- Infobox data (species, gender, origin, status, etc.)
- Main content paragraphs
- Section headings
- Categories

### Search
Search for mascots by name or keyword.

### Browse by Category
List mascots within specific categories such as:
- Olympic Mascots
- Summer Olympic Mascots
- Winter Olympic Mascots
- Brand Mascots
- Animal Mascots
- And many more...

### List All Pages/Categories
Browse all available pages and categories in the wiki.

## Usage Examples

### Get a specific mascot
```json
{
  "function": "get_mascot",
  "name": "Izzy"
}
```

Returns infobox data, content, and sections for Izzy (Atlanta 1996 Olympic mascot).

### Search for mascots
```json
{
  "function": "search_mascots",
  "query": "Olympic",
  "limit": 10
}
```

### List mascots in a category
```json
{
  "function": "list_category",
  "category": "Summer Olympic Mascots",
  "limit": 20
}
```

### List all categories
```json
{
  "function": "list_categories",
  "limit": 50,
  "min_size": 5
}
```

### Get page categories
```json
{
  "function": "get_page_categories",
  "name": "Izzy"
}
```

### List pages with prefix
```json
{
  "function": "list_pages",
  "prefix": "Olympic",
  "limit": 20
}
```

## Data Structure

### Mascot Info (get_mascot)
```json
{
  "name": "Izzy",
  "title": "Izzy",
  "page_id": 3082,
  "url": "https://mascots.fandom.com/wiki/Izzy",
  "infobox": {
    "name": "Izzy",
    "Class": "Event",
    "Species": "Whatizit",
    "Gender": "Male",
    "Date of creation": "1991",
    "Country of origin": "USA",
    "Current status": "Retired",
    "image": "https://static.wikia.nocookie.net/..."
  },
  "content": ["First paragraph...", "Second paragraph..."],
  "sections": [
    {"title": "Name etymology", "anchor": "Name_etymology", "level": "2"},
    {"title": "Appearance", "anchor": "Appearance", "level": "2"},
    ...
  ]
}
```

## Notes

- The skill uses the MediaWiki API directly, bypassing the need for browser automation.
- Page names are case-sensitive but the API handles redirects automatically.
- Categories should be specified without the "Category:" prefix.
- Some pages may be redirects to consolidated pages (e.g., "Miga" redirects to "Miga, Quatchi, Sumi and Mukmuk").
