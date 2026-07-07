# OpenStreetMap Wiki Access Skill

Access structured data from the OpenStreetMap Wiki including UK Areas of Outstanding Natural Beauty (AONB), National Scenic Areas (NSA), and other geographic datasets.

## Overview

This skill provides reliable access to the OpenStreetMap Wiki's structured data tables. The primary use case is extracting the complete UK AONB/NSA dataset with OSM boundary relation IDs for geographic applications.

## Data Available

### UK Areas of Outstanding Natural Beauty (AONB)

- **46 AONBs** across England, Wales, and Northern Ireland
- Scotland has different designations (NSAs, National Parks)

**Fields:**
| Field | Description |
|-------|-------------|
| AONB | Protected landscape name |
| Country | UK constituent country |
| Created | Year designated |
| Boundary Relation | OSM relation ID for boundary |
| Complete | Mapping completion status |
| Notes | Additional information |

**Country breakdown:**
- England: 33 AONBs
- Wales: 4 AONBs  
- Northern Ireland: 8 AONBs
- England and Wales: 1 cross-border AONB

### National Scenic Areas (NSA) - Scotland

- **40 NSAs** in Scotland only
- Different legal designation than AONB

**Fields:**
| Field | Description |
|-------|-------------|
| NSA | Scenic area name |
| Boundary Relation | OSM relation ID |
| Complete | Mapping status |
| Notes | Additional information |

## Functions

### get_aonb_data()

Get all UK AONB and NSA data in a single call.

**Example:**
```python
result = await execute({"function": "get_aonb_data"})
```

**Returns:**
```json
{
  "success": true,
  "title": "Areas of Outstanding Natural Beauty (UK)",
  "aonbs": [
    {
      "AONB": "Cotswolds",
      "Country": "England",
      "Created": "1966",
      "Boundary Relation": "166570",
      "Boundary Relation_osm_id": "166570",
      "Boundary Relation_osm_url": "https://osm.org/relation/166570",
      "Complete": "100%",
      "Notes": "Some sections guesswork"
    },
    // ... 45 more AONBs
  ],
  "nsas": [
    {
      "NSA": "Cairngorm Mountains",
      "Boundary Relation": "",
      "Complete": "",
      "Notes": "within Cairngorms National Park"
    },
    // ... 39 more NSAs
  ],
  "summary": {
    "total_aonbs": 46,
    "total_nsas": 40,
    "aonbs_by_country": {
      "England": 33,
      "Wales": 4,
      "Northern Ireland": 8,
      "England and Wales": 1
    }
  }
}
```

### get_page_tables(page_title, table_class?)

Extract wikitables from any OSM Wiki page.

**Parameters:**
- `page_title` (required): Wiki page title in URL format
- `table_class` (optional): CSS class, defaults to "wikitable"

**Example:**
```python
result = await execute({
    "function": "get_page_tables",
    "page_title": "United_Kingdom"
})
```

### search_pages(search_term, limit?)

Search for wiki pages by keyword.

**Parameters:**
- `search_term` (required): Search query
- `limit` (optional): Max results, defaults to 10

**Example:**
```python
result = await execute({
    "function": "search_pages",
    "search_term": "national park",
    "limit": 20
})
```

## Use Cases

1. **Boundary Mapping**: Get OSM relation IDs to fetch boundary geometries
2. **Geographic Analysis**: Compile protected landscape datasets
3. **OSM Contribution**: Check completion status to prioritize mapping work
4. **Research**: Access authoritative names and designation dates

## Technical Details

- Uses MediaWiki API (`action=parse`) for efficient data retrieval
- Parses HTML tables with BeautifulSoup
- Extracts OSM relation IDs from links (e.g., `https://osm.org/relation/166570`)
- No authentication required
- Rate limiting: Be respectful of the wiki server

## Source

Data source: https://wiki.openstreetmap.org/wiki/Areas_of_Outstanding_Natural_Beauty_(UK)

The OpenStreetMap Wiki is maintained by the OSM community and represents the authoritative source for mapping-related documentation and datasets.