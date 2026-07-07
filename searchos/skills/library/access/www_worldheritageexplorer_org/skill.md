# World Heritage Explorer Access Skill

This skill fetches data about UNESCO World Heritage Sites from [worldheritageexplorer.org](https://www.worldheritageexplorer.org).

## Available Functions

### `get_site`
Fetch detailed information about a specific World Heritage Site.

**Parameters:**
- `site_path` OR `site_slug` (required): The site identifier
  - `site_path`: Full URL path like `/sites/carlsbad_caverns_national_park.html`
  - `site_slug`: Just the slug like `carlsbad_caverns_national_park`

**Returns:**
- Site name, description, coordinates
- World Heritage ID, inscription year
- Category (Natural/Cultural/Mixed)
- Country, continent, UNESCO region
- Area, number of components
- UNESCO inscription criteria
- Links to UNESCO, Wikipedia, Wikidata, IUCN
- JSON-LD structured data

**Example:**
```python
result = await execute({
    "function": "get_site",
    "site_slug": "grand_canyon_national_park"
})
```

### `list_sites`
List all UNESCO World Heritage Sites.

**Parameters:**
- `limit` (optional, default 100): Maximum number of sites to return
- `offset` (optional, default 0): Pagination offset

**Returns:**
- Total count of sites (1,248+)
- Paginated list with site names, slugs, and URLs

**Example:**
```python
result = await execute({
    "function": "list_sites",
    "limit": 50,
    "offset": 0
})
```

### `search_sites`
Search for World Heritage Sites by name.

**Parameters:**
- `query` (required): Search query (case-insensitive partial match)
- `limit` (optional, default 50): Maximum results

**Returns:**
- Matching sites with names, slugs, and URLs

**Example:**
```python
# Find all canyon-related sites
result = await execute({
    "function": "search_sites",
    "query": "canyon"
})

# Find specific site
result = await execute({
    "function": "search_sites",
    "query": "yellowstone"
})
```

## Data Structures

### Site Detail Response
```json
{
  "name": "Grand Canyon National Park",
  "title": "Grand Canyon National Park | World Heritage Explorer",
  "description": "The Grand Canyon National Park...",
  "wh_id": "75",
  "inscription_year": "1979",
  "category": "Natural Heritage",
  "country": "🇺🇸 United States of America",
  "continent": "Americas",
  "geo": {
    "latitude": 36.1008,
    "longitude": -112.0906
  },
  "area": "1,217,262 acres",
  "criteria": "(vii) — Contains superlative natural phenomena... | (viii) — Outstanding example...",
  "links": [
    "https://whc.unesco.org/en/list/75",
    "https://www.wikidata.org/wiki/Q220289",
    "https://en.wikipedia.org/wiki/Grand_Canyon_National_Park"
  ]
}
```

### Site List Entry
```json
{
  "name": "Yellowstone National Park",
  "slug": "yellowstone_national_park",
  "path": "/sites/yellowstone_national_park.html",
  "url": "https://www.worldheritageexplorer.org/sites/yellowstone_national_park.html"
}
```

## Notes

- The site has **1,248 World Heritage Sites** as listed
- All data comes from static HTML pages (no API)
- JSON-LD structured data includes Schema.org TouristAttraction format
- Site slugs use underscores and lowercase (e.g., `machu_picchu`, `taj_mahal`)
- UNESCO Criteria use roman numerals: (i) through (x)

## Related Links

For each site, the skill also provides links to:
- Official UNESCO World Heritage Centre page
- Wikipedia article
- Wikidata entry
- IUCN World Heritage Outlook (for natural sites)