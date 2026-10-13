# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Ancient Egypt Online - Access Skill

This skill fetches encyclopedia articles about Ancient Egyptian history from [Ancient Egypt Online](https://ancientegyptonline.co.uk/).

## About the Site

Ancient Egypt Online is an encyclopedia-style resource covering:
- **Pharaohs and rulers** - Dynasties, kings, and royal figures
- **Monuments** - Pyramids, temples, tombs, and archaeological sites
- **Gods and goddesses** - Egyptian deities and religious beliefs
- **Hieroglyphs** - Writing system and translations
- **Society** - Daily life, culture, and customs
- **History** - Periods from Old Kingdom to Late Period

## Functions

### get_article

Fetch a single article by its URL slug.

**Parameters:**
- `slug` (required): The article's URL slug

**Example slugs:**
- `menkauhor` - Pharaoh Menkauhor
- `black-pyramid-dashur` - Black Pyramid at Dashur
- `intefii` - Intef II
- `khufu` - Pharaoh Khufu
- `great-pyramid` - Great Pyramid of Giza
- `osiris` - God Osiris

**Returns:**
- `title` - Article title
- `sections` - Array of content sections with headings and paragraphs
- `related_links` - Links to related articles
- `full_text` - Complete article text
- `word_count` - Article length

### get_articles

Fetch multiple articles at once.

**Parameters:**
- `slugs` (required): Array of article slugs

**Returns:**
- `articles` - Array of article data
- `successful` - Count of successful fetches
- `failed` - Count of failed fetches

### get_navigation

Get the main site navigation menu.

**Returns:**
- `navigation` - Array of menu items with URLs and labels

### search

Attempt to find an article by name (converts query to slug format).

**Parameters:**
- `query` (required): Search term (e.g., "menkauhor", "black pyramid")

**Note:** This site doesn't have a search API. The search function converts your query to a URL slug format and attempts to fetch that page. For best results, use exact article names.

## Response Structure

### Article Object

```json
{
  "success": true,
  "url": "https://ancientegyptonline.co.uk/menkauhor/",
  "title": "Menkauhor",
  "slug": "menkauhor",
  "sections": [
    {
      "heading": null,
      "level": 0,
      "content": [
        {"type": "paragraph", "text": "..."},
        {"type": "list", "items": ["..."], "ordered": false},
        {"type": "image", "url": "...", "alt": "..."}
      ]
    }
  ],
  "related_links": [
    {"url": "...", "text": "Old Kingdom"}
  ],
  "full_text": "Complete article text...",
  "word_count": 1234
}
```

### Section Content Types

- `paragraph` - Text paragraph
- `list` - Bulleted or numbered list
- `image` - Image with URL, alt text, and optional caption
- `table` - Tabular data

## Usage Tips

1. **Browse by category** - Use `get_navigation` to discover main topic areas
2. **Follow related links** - Each article includes links to related topics
3. **URL patterns** - Slugs are lowercase with hyphens (e.g., `black-pyramid-dashur`)
4. **Categories** - Main categories include: hieroglyphs, thegods, kingslist, monuments, library, society, mysteries

## Example Calls

```json
// Get a single article
{"function": "get_article", "slug": "khufu"}

// Get multiple articles
{"function": "get_articles", "slugs": ["khufu", "menkauhor", "djoser"]}

// Get navigation
{"function": "get_navigation"}

// Search by name
{"function": "search", "query": "great pyramid"}
```
