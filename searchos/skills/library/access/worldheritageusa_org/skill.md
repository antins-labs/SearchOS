# World Heritage USA - Access Skill

This skill provides access to information about U.S. World Heritage Sites from [worldheritageusa.org](https://worldheritageusa.org).

## Overview

The World Heritage USA website documents all 26 UNESCO World Heritage Sites located in the United States. This skill extracts structured data including:

- Site name and description
- State/location
- Inscription year (when added to UNESCO list)
- External links (official site, UNESCO page)
- Featured images

## Available Functions

### list_sites

Returns a list of all site URLs.

```python
result = await execute({'function': 'list_sites'})
# Returns: {'success': True, 'count': 26, 'sites': [...]}
```

### get_site

Fetches detailed information for a specific site by its URL slug.

```python
result = await execute({
    'function': 'get_site',
    'slug': 'yellowstone'
})
# Returns: site details including name, state, inscription year, description, etc.
```

### get_all_sites

Fetches complete details for all sites in one call.

```python
result = await execute({'function': 'get_all_sites'})
# Returns: {'success': True, 'sites': [...]}
```

### search

Searches sites by name, state, or inscription year.

```python
result = await execute({
    'function': 'search',
    'query': 'California'
})
# Returns sites in California

result = await execute({
    'function': 'search',
    'query': '1978'
})
# Returns sites inscribed in 1978
```

## Site Data Structure

Each site entry contains:

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | Full URL to the site page |
| `slug` | string | URL identifier (e.g., 'yellowstone') |
| `name` | string | Site name |
| `state` | string | U.S. state(s) where the site is located |
| `inscription_year` | string | Year added to UNESCO list |
| `description` | string | Site description |
| `image_url` | string | Primary image URL |
| `external_links` | array | Links to official/UNESCO pages |
| `content_images` | array | Additional site images |

## Example Sites

- **Yellowstone National Park** - Wyoming, Montana, Idaho (1978)
- **Statue of Liberty** - New York, New Jersey (1984)
- **Grand Canyon National Park** - Arizona (1979)
- **Independence Hall** - Pennsylvania (1979)
- **Cahokia Mounds** - Illinois (1982)

## Technical Details

- Uses HTTP/HTML scraping with BeautifulSoup
- Extracts JSON-LD structured data when available
- Parses metadata from page content
- No authentication required
- Be respectful with request frequency