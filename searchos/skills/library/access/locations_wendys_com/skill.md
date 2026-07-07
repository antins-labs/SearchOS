# Wendy's Location Finder

SearchOS access skill for retrieving Wendy's restaurant location information from [locations.wendys.com](https://locations.wendys.com).

## Overview

This skill navigates the hierarchical directory structure of Wendy's location finder website to retrieve structured data about:
- US states with Wendy's locations
- Cities within each state with Wendy's restaurants
- Individual Wendy's locations within a city
- Detailed information for specific store locations

## Functions

### `list_states`

Returns a list of all US state codes and names that the skill can query.

**Example:**
```json
{
  "function": "list_states"
}
```

**Response:**
```json
{
  "success": true,
  "count": 51,
  "states": [
    {"code": "AL", "name": "Alabama", "url": "https://locations.wendys.com/united-states/al"},
    {"code": "AK", "name": "Alaska", "url": "https://locations.wendys.com/united-states/ak"},
    ...
  ]
}
```

### `list_cities`

Lists cities within a state that have Wendy's locations.

**Parameters:**
- `state` (required): Two-letter state code (e.g., "NY", "CA", "TX")

**Example:**
```json
{
  "function": "list_cities",
  "state": "NY"
}
```

**Response:**
```json
{
  "success": true,
  "state": "New York",
  "state_code": "NY",
  "total_locations": 236,
  "count": 25,
  "cities": [
    {"name": "Albany", "slug": "albany", "url": "https://locations.wendys.com/united-states/ny/albany"},
    {"name": "Bronx", "slug": "bronx", "url": "https://locations.wendys.com/united-states/ny/bronx"},
    ...
  ]
}
```

### `list_locations`

Lists all Wendy's locations within a city.

**Parameters:**
- `state` (required): Two-letter state code
- `city` (required): City name slug (lowercase, hyphenated)

**Example:**
```json
{
  "function": "list_locations",
  "state": "NY",
  "city": "new-york"
}
```

**Response:**
```json
{
  "success": true,
  "city": "New York, New York",
  "state": "New York",
  "state_code": "NY",
  "count": 11,
  "locations": [
    {
      "name": "111 Fulton Street",
      "slug": "111-fulton-street",
      "url": "https://locations.wendys.com/united-states/ny/new-york/111-fulton-street",
      "phone": "(917) 261-4310"
    },
    ...
  ]
}
```

### `get_location`

Returns detailed information for a specific Wendy's location.

**Parameters:**
- `state` (required): Two-letter state code
- `city` (required): City name slug
- `location` (required): Location identifier slug

**Example:**
```json
{
  "function": "get_location",
  "state": "NY",
  "city": "new-york",
  "location": "111-fulton-street"
}
```

**Response:**
```json
{
  "success": true,
  "location": {
    "name": "Wendy's 111 FULTON in New York, NY",
    "street_address": "111 Fulton Street",
    "city": "New York",
    "state": "NY",
    "postal_code": "10038",
    "country": "US",
    "phone": "(917) 261-4310",
    "latitude": "40.70986215696315",
    "longitude": "-74.00665035655425",
    "hours": {
      "MONDAY": ["6:30 AM - 1:00 AM (next day)"],
      "TUESDAY": ["6:30 AM - 1:00 AM (next day)"],
      ...
    },
    "url": "https://locations.wendys.com/united-states/ny/new-york/111-fulton-street"
  }
}
```

## URL Structure

The Wendy's location website uses a hierarchical URL structure:
- States: `/united-states/{state-code}`
- Cities: `/united-states/{state-code}/{city-slug}`
- Locations: `/united-states/{state-code}/{city-slug}/{location-slug}`

For example:
- `https://locations.wendys.com/united-states/ny`
- `https://locations.wendys.com/united-states/ny/new-york`
- `https://locations.wendys.com/united-states/ny/new-york/111-fulton-street`

## Data Extraction

The skill extracts data from the website's HTML pages using:
- BeautifulSoup for HTML parsing
- Meta tags (itemprop) for address components and coordinates
- Data attributes for hours information
- Structured directory links for navigation

## Hours Format

Hours are extracted from the `data-days` attribute and converted from military time format (e.g., 630 = 6:30 AM, 100 = 1:00 AM next day) to readable 12-hour format.

## Notes

- All location slugs should be lowercase with hyphens replacing spaces
- Some cities may have multiple Wendy's locations
- Location details include coordinates (latitude/longitude) when available
- Phone numbers are extracted from itemprop="telephone" elements