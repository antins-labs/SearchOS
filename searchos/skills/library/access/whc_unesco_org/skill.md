# UNESCO World Heritage Centre Access Skill

Access the UNESCO World Heritage Convention database to retrieve information about World Heritage Sites, States Parties statistics, and more.

## Overview

This skill provides programmatic access to the UNESCO World Heritage Centre (whc.unesco.org) database, including:

- **World Heritage List**: All 1,200+ properties on the World Heritage List
- **Sites in Danger**: Properties on the List of World Heritage in Danger
- **States Parties**: Country-level statistics and convention participation
- **Search**: Full-text search across site names

## Available Functions

### list_sites

List World Heritage sites with optional filters.

**Parameters:**
- `country_code` (optional): ISO 3166-1 alpha-2 country code (e.g., 'us', 'fr', 'jp')
- `category` (optional): 'cultural', 'natural', or 'mixed'
- `in_danger` (optional): Boolean to filter sites in danger
- `limit` (optional): Maximum results (default: 100)

**Example:**
```
function: list_sites
country_code: us
category: natural
```

### get_site

Get details for a specific World Heritage site.

**Parameters:**
- `site_id` (required): UNESCO site ID number

**Example:**
```
function: get_site
site_id: 1466
```

### get_country_stats

Get World Heritage statistics for a specific country.

**Parameters:**
- `country_code` (required): ISO 3166-1 alpha-2 country code

**Example:**
```
function: get_country_stats
country_code: fr
```

Returns:
- `properties_inscribed`: Number of World Heritage properties
- `mandates`: Times served on World Heritage Committee
- `conservation_reports`: State of Conservation reports
- `assistance_requests`: International assistance requests approved
- `ratification_date`: Date of convention ratification

### get_statistics

Get overall World Heritage statistics.

**Returns:**
- Total sites worldwide
- Sites by category (Cultural, Natural, Mixed)
- Total sites in danger
- Number of countries with sites

### search_sites

Search World Heritage sites by name.

**Parameters:**
- `query` (required): Search term
- `country_code` (optional): Filter by country
- `limit` (optional): Maximum results (default: 50)

**Example:**
```
function: search_sites
query: pyramid
```

## Data Sources

The skill uses the following API endpoints discovered on the site:

1. **GeoJSON API**: `GET /en/list/?mode=geojson`
   - Returns all sites with coordinates and metadata
   - Supports filtering by country, category, region, danger status, and search term

2. **RSS Feed**: `GET /en/list/rss`
   - Alternative site listing in XML format

3. **States Parties Pages**: `GET /en/statesparties/{country_code}`
   - Country statistics scraped from HTML

## Site Data Structure

Each site returned includes:

```json
{
  "id": 1466,
  "title": "San Antonio Missions",
  "category": "Cultural",
  "category_id": 1,
  "in_danger": false,
  "country": "United States of America",
  "geometry_type": "Point",
  "coordinates": [-98.46, 29.3280555556],
  "components": [
    {"name": "Mission Espada", "country": "United States of America"}
  ]
}
```

## Categories

- **Cultural** (cat_id: 1): Cultural heritage sites
- **Natural** (cat_id: 2): Natural heritage sites
- **Mixed** (cat_id: 3): Sites with both cultural and natural significance

## Country Codes

Use ISO 3166-1 alpha-2 codes:
- `us` - United States
- `fr` - France
- `jp` - Japan
- `cn` - China
- `de` - Germany
- `it` - Italy
- `es` - Spain
- etc.

## Examples

### List all sites in France

```python
result = await execute({
    "function": "list_sites",
    "country_code": "fr"
})
```

### Find natural sites in danger

```python
result = await execute({
    "function": "list_sites",
    "category": "natural",
    "in_danger": true
})
```

### Search for pyramid-related sites

```python
result = await execute({
    "function": "search_sites",
    "query": "pyramid"
})
```

### Get statistics for Japan

```python
result = await execute({
    "function": "get_country_stats",
    "country_code": "jp"
})
```

## Limitations

- Individual site detail pages are protected by Cloudflare, so detailed descriptions are not available through this API
- GeoJSON data provides basic site information only
- Some serial properties have multiple component locations

## Rate Limiting

Please be respectful of UNESCO's servers. The skill implements conservative rate limits:
- 2 requests per second
- 30 requests per minute