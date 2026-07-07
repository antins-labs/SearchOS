# English Heritage Property Information Access Skill

This skill extracts detailed prices, opening times, and information from English Heritage property pages.

## Overview

The English Heritage website (www.english-heritage.org.uk) provides information about hundreds of historic properties across England. This skill extracts comprehensive details including:

- Opening times and seasonal variations
- Ticket prices (adult, child, concession, family)
- Peak/off-peak/standard pricing tiers
- Gift aid pricing options
- Opening time periods and dates
- Property locations and descriptions

## Data Sources

### Primary: Property API

When available (from `/prices-and-opening-times/` pages), the skill uses the official API:

```
GET https://www.english-heritage.org.uk/api/propertypricesopeningtimes/{property_id}
```

This returns structured JSON with:
- Complete opening times for all date periods
- Full pricing information (standard, peak, off-peak, gate prices)
- Gift aid options
- Date ranges for seasonal pricing

### Fallback: HTML Extraction

For main property pages or when the API is unavailable, the skill extracts data from HTML:
- Opening times from `.property-Opening` elements
- Starting prices from `.price` elements
- Property name, address, and geo from JSON-LD structured data
- Links to full prices and opening times page

## Functions

### get_property_info

Get detailed information for a single property.

**Parameters:**
- `url` (string): Full URL to a property page (either main page or prices-and-opening-times page)
- `property_slug` (string): Property slug from URL (e.g., 'stonehenge') - alternative to URL

**Example:**
```python
# Using full URL
result = await execute({
    'function': 'get_property_info',
    'url': 'https://www.english-heritage.org.uk/visit/places/stonehenge/'
})

# Using slug
result = await execute({
    'function': 'get_property_info',
    'property_slug': 'dover-castle'
})
```

**Response Structure (API data):**
```json
{
  "success": true,
  "data": {
    "data_source": "api",
    "api_available": true,
    "property_id": "181968",
    "name": "Jewel Tower",
    "valid_from": "2026-06-21T00:00:00",
    "valid_to": "2027-03-16T00:00:00",
    "opening_times": {
      "periods": [...],
      "current": {
        "start_date": "2026-06-22",
        "end_date": "2026-08-30",
        "times": {
          "monday": "10:00 - 17:00",
          "tuesday": "10:00 - 17:00",
          ...
        }
      }
    },
    "prices": {
      "free_to_enter": false,
      "prices": {
        "adult": {"standard": "£7.65", "with_gift_aid": "£8.50"},
        "child": {"standard": "£3.82", "with_gift_aid": "£4.25"},
        "family_2_adults": {"standard": "£19.29", "with_gift_aid": "£21.25"}
      },
      "seasonal_pricing": {
        "peak": {"adult": "£8.50", "child": "£4.25"},
        "off_peak": {"adult": "£6.88", "child": "£3.40"}
      },
      "gate_prices": {"adult": "£9.00", ...}
    }
  }
}
```

**Response Structure (HTML extraction):**
```json
{
  "success": true,
  "data": {
    "data_source": "html_extraction",
    "api_available": false,
    "name": "Stonehenge",
    "address": {
      "addressLocality": "Near Amesbury",
      "addressRegion": "Wiltshire",
      "postalCode": "SP4 7DE"
    },
    "opening_times": {
      "raw_text": "Mon - Sun 9.30am - 6pm (last entry at 4pm)",
      "parsed": {
        "open_time": "9.30am",
        "close_time": "6pm"
      }
    },
    "price_from": "£6.00",
    "prices_page": "https://www.english-heritage.org.uk/visit/places/stonehenge/prices-and-opening-times/"
  }
}
```

### get_properties_list

Get information for multiple properties in a single call.

**Parameters:**
- `properties` (array): List of property objects with `url` or `slug` keys

**Example:**
```python
result = await execute({
    'function': 'get_properties_list',
    'properties': [
        {'slug': 'stonehenge'},
        {'slug': 'dover-castle'},
        {'url': 'https://www.english-heritage.org.uk/visit/places/jewel-tower/'}
    ]
})
```

**Response:**
```json
{
  "success": true,
  "count": 3,
  "results": [
    {
      "input": {"slug": "stonehenge"},
      "status": "success",
      "data": {...}
    },
    ...
  ]
}
```

## Usage Notes

1. **API Availability**: Properties that use the Ventrata booking system (like Stonehenge) may not have the full API available, falling back to HTML extraction.

2. **Seasonal Pricing**: The API provides comprehensive seasonal pricing with peak/off-peak/standard tiers and date ranges for each period.

3. **Opening Times**: The API returns detailed opening times per day for each date period, including the current applicable period.

4. **Gift Aid**: UK visitors can add a voluntary donation (Gift Aid), which is tracked separately in the API response.

## Error Handling

The skill returns structured error responses rather than raising exceptions:

```json
{
  "success": false,
  "error": "Could not fetch property information",
  "url": "https://..."
}
```

Common errors:
- Invalid URL or slug
- Network timeout
- Page not found (404)
- Rate limiting

## Supported Properties

This skill works with any English Heritage property page, including:
- Stonehenge
- Dover Castle
- Tintagel Castle
- Hadrian's Wall
- Battle Abbey
- Osborne
- And 400+ other historic sites

Find all properties at: https://www.english-heritage.org.uk/visit/places/