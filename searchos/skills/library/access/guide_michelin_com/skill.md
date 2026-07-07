# Michelin Guide Restaurant Search Skill

Access the complete Michelin Guide restaurant database via Algolia API.

## Overview

This skill provides direct API access to the Michelin Guide restaurant database, allowing you to:
- Search for restaurants by name, location, or keywords
- Filter by Michelin distinction (1-3 stars, Bib Gourmand, Plate)
- Find restaurants near geographic coordinates
- Get detailed restaurant information including images, hours, and booking links

## Functions

### 1. search

Search for restaurants with various filters.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| query | string | No | Restaurant name, chef name, or keywords |
| city | string | No | City name (e.g., "Paris", "New York", "Tokyo") |
| country | string | No | Country name or code (e.g., "France", "FR") |
| distinction | string | No | Michelin distinction filter |
| cuisine | string | No | Cuisine type (e.g., "French", "Japanese") |
| green_star | boolean | No | Filter for sustainable restaurants |
| page | integer | No | Page number (default 0) |
| limit | integer | No | Results per page (default 20, max 100) |

**Distinction Options:**
- `"3-stars"`, `"3-star"`, `"three-stars"` → 3 Stars MICHELIN
- `"2-stars"`, `"2-star"`, `"two-stars"` → 2 Stars MICHELIN
- `"1-star"`, `"one-star"` → 1 Star MICHELIN
- `"bib-gourmand"`, `"bib"` → Bib Gourmand
- `"plate"`, `"michelin-plate"` → The Plate MICHELIN

**Examples:**

```json
// Find all 3-star restaurants in Paris
{
  "function": "search",
  "city": "paris",
  "distinction": "3-stars"
}

// Search for Japanese restaurants in France with Michelin stars
{
  "function": "search",
  "country": "france",
  "cuisine": "japanese",
  "distinction": "1-star"
}

// Search by restaurant name
{
  "function": "search",
  "query": "Eleven Madison Park"
}

// Get all Bib Gourmand restaurants
{
  "function": "search",
  "distinction": "bib-gourmand",
  "limit": 50
}
```

### 2. get_by_slug

Get detailed information about a specific restaurant using its URL slug.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| slug | string | Yes | Restaurant slug or URL path |

**Examples:**

```json
// Get restaurant by slug
{
  "function": "get_by_slug",
  "slug": "epicure"
}

// Also accepts full URL paths
{
  "function": "get_by_slug",
  "slug": "/us/en/ile-de-france/paris/restaurant/plenitude-cheval-blanc-paris"
}
```

### 3. search_by_location

Find restaurants near geographic coordinates.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| lat | number | Yes | Latitude |
| lng | number | Yes | Longitude |
| radius | integer | No | Search radius in meters (default 5000) |
| distinction | string | No | Optional Michelin distinction filter |
| limit | integer | No | Number of results (default 20, max 100) |
| page | integer | No | Page number (default 0) |

**Examples:**

```json
// Find restaurants within 2km of Eiffel Tower
{
  "function": "search_by_location",
  "lat": 48.8584,
  "lng": 2.2945,
  "radius": 2000
}

// Find 3-star restaurants within 5km of central Tokyo
{
  "function": "search_by_location",
  "lat": 35.6762,
  "lng": 139.6503,
  "distinction": "3-stars"
}
```

### 4. get_filters

Get available filter options with counts.

**Parameters:** None

**Example:**
```json
{
  "function": "get_filters"
}
```

Returns lists of available distinctions, cuisines, and price categories with counts.

## Response Structure

### Restaurant Object

```json
{
  "id": "6106",
  "name": "Épicure",
  "slug": "epicure",
  "url": "https://guide.michelin.com/en/ile-de-france/paris/restaurant/epicure",
  "short_link": "https://guide.michelin.com/r/6106",
  
  "michelin_award": "THREE_STARS",
  "michelin_star": "THREE",
  "distinction": {
    "label": "Three Stars: Exceptional cuisine",
    "slug": "3-stars-michelin",
    "display_name": "3 Stars MICHELIN"
  },
  "guide_year": 2026,
  
  "location": {
    "address": "Le Bristol, 112 rue du Faubourg-Saint-Honoré",
    "city": "Paris",
    "city_slug": "paris",
    "region": "Ile-de-France",
    "country": "France",
    "country_code": "FR",
    "postcode": "75008",
    "full_address": "Le Bristol, 112 rue du Faubourg-Saint-Honoré, Paris, 75008, France",
    "coordinates": {
      "lat": 48.8717223,
      "lng": 2.3145978
    }
  },
  
  "cuisines": ["Modern Cuisine"],
  "phone": "+33 1 53 43 43 40",
  "website": "https://www.oetkerhotels.com/fr/hotels/le-bristol-paris/restaurants-bars/epicure/",
  
  "price": {
    "low": null,
    "high": null,
    "category": "Spare no expense",
    "category_slug": "luxury",
    "currency": "EUR",
    "currency_symbol": "€"
  },
  
  "main_image": "https://axwwgrkdco.cloudimg.io/v7/__gmpics3__/07313ddb006f438b9d82cd8bfc1d9f7a.jpg",
  "images": [
    {
      "url": "...",
      "copyright": "Thomas Dhellemmes/Épicure",
      "topic": "SUJ_ENT"
    }
  ],
  
  "chef": null,
  
  "booking": {
    "available": true,
    "provider": "TheFork",
    "url": "https://module.thefork.com/..."
  },
  
  "facilities": [],
  "take_away": false,
  "delivery": false,
  "green_star": null,
  
  "description": "Le Bristol is the quintessence of luxury..."
}
```

## Common Use Cases

### Find Michelin-starred restaurants in a city

```json
{
  "function": "search",
  "city": "tokyo",
  "distinction": "3-stars"
}
```

### Search for a specific restaurant by name

```json
{
  "function": "search",
  "query": "Noma"
}
```

### Get all restaurants with a specific cuisine in a country

```json
{
  "function": "search",
  "country": "italy",
  "cuisine": "sushi"
}
```

### Find sustainable (Green Star) restaurants

```json
{
  "function": "search",
  "green_star": true
}
```

### Discover restaurants near a landmark

```json
{
  "function": "search_by_location",
  "lat": 51.5007,
  "lng": -0.1246,
  "radius": 1000
}
```

## Notes

- The Michelin Guide uses Algolia for search; this skill makes direct API calls
- Restaurant `slug` values can be extracted from Michelin Guide URLs
- Images include copyright information that should be respected
- Not all restaurants have chef names, price ranges, or booking availability
- The `guide_year` indicates which Michelin Guide edition the restaurant appears in
- Booking providers include TheFork, Resy, OpenTable, and direct restaurant bookings

## Error Handling

All responses include a `success` boolean field. When `false`, an `error` field describes the issue:

```json
{
  "success": false,
  "error": "Restaurant not found with slug: unknown-restaurant"
}
```

Common errors:
- Missing required parameters
- Invalid distinction or cuisine filters
- Restaurant slug not found
- API rate limiting (very rare with Algolia)