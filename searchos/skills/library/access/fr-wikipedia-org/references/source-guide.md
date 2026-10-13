# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# French Wikipedia Access Skill

This skill extracts structured information from French Wikipedia (fr.wikipedia.org) pages.

## Features

### get_page_info
Retrieves comprehensive page information including:
- Page title and URL
- Introduction paragraph(s)
- Infobox data (for biographical pages)
- All wikitable tables
- Section structure
- Categories
- Internal links

**Parameters:**
- `url` (optional): Full Wikipedia URL
- `title` (optional): Page title (will be converted to URL)

**Example:**
```json
{
  "function": "get_page_info",
  "title": "Jacques Chaban-Delmas"
}
```

### get_infobox
Extracts detailed information from biographical infoboxes:
- Person's name and image
- Political positions and mandates
- Dates and durations
- Predecessors/successors
- Raw field-value pairs

**Parameters:**
- `url` (optional): Full Wikipedia URL
- `title` (optional): Page title

**Example:**
```json
{
  "function": "get_infobox",
  "url": "https://fr.wikipedia.org/wiki/Michel_Debre"
}
```

### get_tables
Extracts all wikitable tables from a page:
- Table headers and captions
- Row data
- Election results
- Mandate histories

**Parameters:**
- `url` (optional): Full Wikipedia URL
- `title` (optional): Page title

**Example:**
```json
{
  "function": "get_tables",
  "title": "Jacques Chaban-Delmas"
}
```

### get_section
Retrieves content from a specific section:
- Section headlines
- Paragraph text content

**Parameters:**
- `url` (optional): Full Wikipedia URL
- `title` (optional): Page title
- `section` (required): Section name (supports partial matching)

**Example:**
```json
{
  "function": "get_section",
  "title": "Démission du gouvernement français",
  "section": "Présidence de Charles de Gaulle"
}
```

### search
Searches French Wikipedia for pages matching a query.

**Parameters:**
- `query` (required): Search query
- `limit` (optional): Maximum results (default: 10)

**Example:**
```json
{
  "function": "search",
  "query": "Premier ministre France",
  "limit": 5
}
```

## Use Cases

This skill is particularly useful for:
- Extracting biographical information about French politicians
- Getting structured data from political mandate tables
- Researching French government history
- Parsing election results from Wikipedia tables
- Understanding the structure of government resignations

## Notes

- Pages are fetched using Playwright for reliable rendering
- French locale is set for proper content display
- Text is cleaned and normalized (extra whitespace removed, edit links removed)
- Infobox data is structured by mandate/position for easy parsing
- Tables are returned with headers and row data as arrays
