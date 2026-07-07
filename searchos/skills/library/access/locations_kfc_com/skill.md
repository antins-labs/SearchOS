# KFC Store Locator Access Skill

This skill fetches KFC restaurant location data from the official KFC store locator at [locations.kfc.com](https://locations.kfc.com).

## Features

- **State listing**: Get a list of all US state codes for building queries
- **City listing**: Retrieve all cities/towns with KFC locations in a state
- **Store listing**: Get all KFC stores in a specific city
- **Store details**: Fetch detailed information for a specific store including:
  - Store name and address
  - Phone number
  - GPS coordinates (latitude/longitude)
  - Available services (Delivery, WiFi, Catering, Gift Cards, etc.)
  - Operating hours
  - Store URL

## Usage Examples

### List all available states
```python
result = await execute({'function': 'list_states'})
# Returns: {'states': [{'code': 'ny', 'name': 'New York'}, ...], 'count': 51}
```

### List cities in a state
```python
result = await execute({'function': 'list_cities', 'state': 'ny'})
# Returns cities with URLs and indicates if it's a city page or direct store link
# {
#   'title': '166 KFC Locations in New York',
#   'cities': [
#     {'name': 'Albany', 'url': '...', 'type': 'city'},
#     {'name': 'Bronx', 'url': '...', 'type': 'city'},
#     ...
#   ]
# }
```

### List stores in a city
```python
result = await execute({'function': 'list_stores', 'city_path': 'ny/bronx'})
# Returns:
# {
#   'title': '7 KFC Locations in Bronx',
#   'stores': [
#     {
#       'name': 'KFC 1125 E Gun Hill Rd',
#       'url': 'https://locations.kfc.com/ny/bronx/1125-e-gun-hill-rd',
#       'address': '1125 E Gun Hill Rd Bronx, NY 10469',
#       'phone': '+17186544440',
#       'hours_status': 'Open Now: Closes at 10:00 PM'
#     },
#     ...
#   ]
# }
```

### Get detailed store information
```python
result = await execute({
    'function': 'get_store',
    'store_url': 'https://locations.kfc.com/ny/new-york/2-penn-plaza'
})
# Returns:
# {
#   'name': 'Kentucky Fried Chicken - New York, NY - 2 Penn Plaza',
#   'address': '2 Penn Plaza, New York, NY 10121',
#   'phone': '+12126300320',
#   'latitude': '40.750041',
#   'longitude': '-73.992211',
#   'services': ['Catering', 'WiFi', 'Gift Cards', 'Delivery'],
#   'hours': {
#     'Monday': '10:00 AM - 11:00 PM',
#     'Tuesday': '10:00 AM - 11:00 PM',
#     ...
#   }
# }
```

### Auto-detect page type
```python
result = await execute({'function': 'fetch', 'path': '/ca/los-angeles'})
# Automatically detects if the path is a state, city, or store page
# Returns appropriate data based on page type
```

## Data Structure

### State Page Response
- `title`: Page title with location count
- `total_locations`: Total number of KFC locations in the state
- `cities`: Array of city/location objects with name, URL, and type
- `count`: Number of items in the cities array

### City Page Response
- `title`: Page title with store count
- `stores`: Array of store objects
- `count`: Number of stores

### Store Detail Response
- `name`: Full store name
- `address`: Street address
- `phone`: Phone number (formatted)
- `latitude`, `longitude`: GPS coordinates
- `services`: Array of available services
- `hours`: Object mapping days to operating hours
- `url`: Store detail page URL

## Notes

- All state codes should be lowercase (e.g., 'ny' not 'NY')
- City names in URLs are lowercase with hyphens (e.g., 'new-york', 'los-angeles')
- Store URLs contain the store slug derived from the street address
- The `fetch` function is useful when you're unsure of the page type
- Some small cities may link directly to a single store instead of a city page