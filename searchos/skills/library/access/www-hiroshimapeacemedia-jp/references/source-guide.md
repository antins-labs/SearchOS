# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Hiroshima Peace Media - Peace Museums of the World

This skill provides structured access to the **Peace Museums of the World** directory maintained by the Hiroshima Peace Media Center (Chugoku Shimbun). The directory catalogs peace museums globally, organized by region.

## Available Functions

### `list_museums`
Lists all peace museums organized by region (Japan, Asia, Africa, Europe, Americas, Oceania).

**Optional Parameters:**
- `region` - Filter by region name (e.g., "JAPAN", "EUROPE")
- `country` - Filter by country name (e.g., "France", "India")

**Returns:**
- List of regions, each containing museums with name, URL, slug, and country (for non-Japan regions)
- Total museum count

**Example:**
```python
# List all museums
execute({"function": "list_museums"}, ctx)

# List museums in Europe
execute({"function": "list_museums", "region": "EUROPE"}, ctx)

# List museums in China
execute({"function": "list_museums", "country": "China"}, ctx)
```

### `get_museum`
Retrieves detailed information about a specific museum.

**Required Parameters (one of):**
- `slug` - Museum page identifier (e.g., "20080526231943237_en")
- `url` - Full URL to the museum page

**Returns:**
- Museum title, region, date, author
- Full description
- Contact information (address, phone, fax, homepage)
- Opening hours, closed days, admission fees
- Photo gallery with captions
- Related museums in the same region

**Example:**
```python
# Get Hiroshima Peace Memorial Museum
execute({"function": "get_museum", "slug": "20080526231943237_en"}, ctx)

# Or use full URL
execute({"function": "get_museum", "url": "https://www.hiroshimapeacemedia.jp/mediacenter_d/w_museum/20080526231943237_en.html"}, ctx)
```

### `search_museums`
Search museums by name or country.

**Required Parameters:**
- `query` - Search term

**Returns:**
- Matching museums with region, name, URL, slug, and country

**Example:**
```python
# Search for "atomic"
execute({"function": "search_museums", "query": "atomic"}, ctx)

# Search for museums in Germany
execute({"function": "search_museums", "query": "Germany"}, ctx)
```

### `get_regions`
Get a summary of all regions with museum counts.

**Returns:**
- List of regions with museum counts
- Total museum count

**Example:**
```python
execute({"function": "get_regions"}, ctx)
```

## Data Structure

### Museum Listing
```json
{
  "name": "Hiroshima Peace Memorial Museum",
  "url": "https://www.hiroshimapeacemedia.jp/mediacenter_d/w_museum/20080526231943237_en.html",
  "slug": "20080526231943237_en",
  "country": null  // Japan museums don't have country field
}
```

### Museum Detail
```json
{
  "title": "Hiroshima Peace Memorial Museum (Japan)",
  "region": "JAPAN",
  "date": "(Aug. 1, 2008)",
  "author": "by Megumi Yamada, Curatorial Division of Hiroshima Peace Memorial Museum",
  "description": "The world's first atomic bomb was dropped on Hiroshima...",
  "address": "1-2 Nakajima-cho, Naka-ku, Hiroshima",
  "phone": "+81-82-241-4004",
  "homepage": "http://www.pcf.city.hiroshima.jp/top_e.html",
  "hours": "...",
  "days_closed": "Dec.29-Jan. 1",
  "admission": "Adults (College students and up) ¥50 ...",
  "photos": [
    {
      "thumbnail": "...",
      "original": "...",
      "caption": "..."
    }
  ]
}
```

## Source

Data is fetched from: https://www.hiroshimapeacemedia.jp/mediacenter_d/w_museum/

The site is maintained by The Chugoku Shimbun (中国新聞社) as part of the Hiroshima Peace Media Center.
