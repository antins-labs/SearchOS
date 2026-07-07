# World Heritage Datasheets - UNEP-WCMC

Access detailed information about natural and mixed World Heritage Sites from the UNEP-WCMC World Heritage Datasheets database.

## Overview

This skill provides access to the [UNEP-WCMC World Heritage Datasheets](http://world-heritage-datasheets.unep-wcmc.org/), a comprehensive database containing detailed information about natural and mixed World Heritage Sites worldwide. The datasheets provide authoritative information on site characteristics, conservation values, management, threats, and protection status.

## Available Functions

### list_sites

List all World Heritage sites in the database.

**Parameters:** None

**Returns:**
- `success`: Boolean indicating success
- `count`: Total number of sites
- `sites`: Array of site objects with:
  - `name`: Site name
  - `slug`: URL slug for the site
  - `url`: Full URL to the site page

**Example:**
```python
result = await execute({"function": "list_sites"})
# Returns list of 237+ World Heritage sites
```

---

### get_site

Get detailed information about a specific World Heritage site.

**Parameters:**
- `site_slug` (required): URL slug of the site (e.g., 'olympic-national-park')

**Returns:**
- `success`: Boolean indicating success
- `site`: Object containing:
  - `title`: Full site name
  - `slug`: URL slug
  - `url`: Full URL
  - `description`: Site description/statement of significance
  - `inscription_year`: Year inscribed on World Heritage List
  - `sections`: Dictionary of detailed sections including:
    - Natural World Heritage Serial Site / Natural World Heritage Site
    - Statement of Outstanding Universal Value
    - International Designation
    - IUCN Management Category
    - Biogeographical Province
    - Geographical Location
    - Dates and History of Establishment
    - Land Tenure
    - Area
    - Altitude
    - Physical Features
    - Climate
    - Vegetation
    - Fauna
    - Cultural Heritage
    - Local Human Population
    - Visitors and Visitor Facilities
    - Scientific Research and Facilities
    - Conservation Value
    - Conservation Status and Management
    - Management Constraints
    - Staff
    - Budget
    - IUCN Management Category
    - Further Reading

**Example:**
```python
result = await execute({
    "function": "get_site",
    "site_slug": "olympic-national-park"
})
```

---

### search

Search for World Heritage sites by keyword.

**Parameters:**
- `query` (required): Search query string

**Returns:**
- `success`: Boolean indicating success
- `query`: The search query
- `total_count`: Total number of matching results
- `results`: Array of matching sites with name, slug, and url

**Example:**
```python
result = await execute({
    "function": "search",
    "query": "national park"
})
```

---

### list_countries

List all countries with World Heritage sites and their site counts.

**Parameters:** None

**Returns:**
- `success`: Boolean indicating success
- `count`: Total number of countries
- `countries`: Array of country objects with:
  - `name`: Country name
  - `site_count`: Number of World Heritage sites

**Example:**
```python
result = await execute({"function": "list_countries"})
```

---

### get_sites_by_country

Get all World Heritage sites for a specific country.

**Parameters:**
- `country` (required): Country name (case-insensitive, e.g., 'United States of America')

**Returns:**
- `success`: Boolean indicating success
- `country`: Country name
- `site_count`: Number of sites in the country
- `sites`: Array of site objects with name, slug, and url

**Example:**
```python
result = await execute({
    "function": "get_sites_by_country",
    "country": "United States of America"
})
```

## Data Sources

All data is sourced from:
- **Base URL**: http://world-heritage-datasheets.unep-wcmc.org/
- **Provider**: UNEP World Conservation Monitoring Centre (UNEP-WCMC)
- **Authority**: International Union for Conservation of Nature (IUCN)

## Content Coverage

The database includes:
- 237+ natural and mixed World Heritage Sites
- Sites from 90+ countries worldwide
- Comprehensive information on:
  - Inscription criteria and history
  - Geographic and ecological characteristics
  - Conservation values and biodiversity
  - Management status and challenges
  - Threats and protection measures

## Site URL Patterns

Sites can be accessed using their slug in the URL:
```
http://world-heritage-datasheets.unep-wcmc.org/datasheet/output/site/{site-slug}
```

Slug format: lowercase, hyphen-separated name (e.g., 'yellowstone-national-park', 'great-barrier-reef')

## Error Handling

All functions return consistent error responses:
```python
{
    "success": false,
    "error": "Error message",
    "error_code": "ERROR_CODE"
}
```

Common error codes:
- `MISSING_PARAMETER`: Required parameter not provided
- `MISSING_FUNCTION`: No function specified
- `UNKNOWN_FUNCTION`: Invalid function name
- `NOT_FOUND`: Requested resource not found
- `FETCH_ERROR`: Network or server error

## Rate Limits

Please respect reasonable rate limits (recommended: 2 requests per second) to avoid overloading the server.

## Use Cases

1. **Research**: Access detailed conservation and management information for World Heritage Sites
2. **Planning**: Review site characteristics for travel or research planning
3. **Education**: Learn about natural heritage sites worldwide
4. **Conservation**: Monitor conservation status and management constraints
5. **Comparative Studies**: Compare sites across countries and regions