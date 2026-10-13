# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Olympic Design Access Skill

This skill retrieves structured data about Olympic Games mascots and emblems from [theolympicdesign.com](https://www.theolympicdesign.com).

## Available Functions

### `get_record`
Fetch a single Olympic design record by URL or slug.

**Parameters:**
- `url` (string, optional): Full URL of the record page
- `slug` (string, optional): Record identifier (e.g., `atlanta-1996`, `london-2012`)
- `category` (string, optional): Either `mascots` or `emblems` (default: `mascots`)

**Example:**
```json
{
  "function": "get_record",
  "slug": "atlanta-1996",
  "category": "mascots"
}
```

**Returns:**
- `title`: The official title (e.g., "Atlanta 1996 – Mascot Izzy")
- `designer`: Designer name(s) if available
- `og_image`: Main promotional image URL
- `gallery_images`: Array of high-resolution gallery images
- `main_images`: Array of main design images
- `sports`: List of associated sports (for mascots)
- `breadcrumb`: Navigation breadcrumb
- `url`: Source URL

---

### `list_records`
List all available records for a category.

**Parameters:**
- `category` (string): Either `mascots` or `emblems`

**Example:**
```json
{
  "function": "list_records",
  "category": "mascots"
}
```

**Returns:**
- `total`: Total number of records
- `records`: Array of `{slug, url, category, text}` objects

---

### `search_records`
Search for records by city name or year.

**Parameters:**
- `query` (string): Search term (city name or year)
- `category` (string, optional): Filter by `mascots` or `emblems`

**Example:**
```json
{
  "function": "search_records",
  "query": "london"
}
```

**Returns:**
- `total`: Number of matching records
- `results`: Array of matching record metadata

---

### `get_multiple_records`
Fetch multiple records at once.

**Parameters:**
- `slugs` (array of strings): Record identifiers
- `urls` (array of strings, optional): Full URLs
- `category` (string, optional): Either `mascots` or `emblems` (default: `mascots`)

**Example:**
```json
{
  "function": "get_multiple_records",
  "slugs": ["atlanta-1996", "london-2012", "beijing-2008"],
  "category": "mascots"
}
```

---

## Data Coverage

### Mascots (33 records)
Includes Olympic mascots from Grenoble 1968 to Paris 2024, featuring famous mascots like:
- Izzy (Atlanta 1996)
- Wenlock & Mandeville (London 2012)
- Fuwa (Beijing 2008)
- And many more...

### Emblems (62 records)
Includes Olympic emblems/coat of arms from Athens 1896 to future games like Los Angeles 2028.

---

## Notes

- The site uses Jimdo CMS with consistent page structure
- Each record includes designer attribution when available
- Gallery images are extracted at 2048x2048 resolution
- Some mascot pages include sport-specific design variants
- All image URLs are from Jimdo's CDN (image.jimcdn.com)
