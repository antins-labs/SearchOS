# EDMO (European Directory of Marine Organisations) Access Skill

This skill provides access to the SeaDataNet EDMO database, which contains information about marine and oceanographic organizations worldwide.

## What is EDMO?

The European Directory of Marine Organisations (EDMO) is a comprehensive database maintained by SeaDataNet containing information about organizations involved in marine and oceanographic research, data management, and related activities worldwide.

## Available Functions

### 1. `get_organization`

Fetch detailed information about a specific organization by its EDMO ID.

**Parameters:**
- `edmo_id` (required): The EDMO record ID (e.g., "4830")

**Returns:**
- Organization details including name, address, contact information, coordinates, website
- Related services (CSR, EDMERP, EDMED, etc.)
- Metadata including update date and collating centre

**Example:**
```python
result = await execute({
    'function': 'get_organization',
    'edmo_id': '4830'
})
```

### 2. `search_organizations`

Search for organizations by name and/or country.

**Parameters:**
- `name` (optional): Organization name search string (supports partial matching)
- `country` (optional): Country name or code (e.g., "Switzerland" or "218")
- `existing_only` (optional, default "true"): Only return currently existing organizations
- `limit` (optional): Maximum number of results to return

**Note:** At least one of `name` or `country` must be provided.

**Example:**
```python
# Search by name
result = await execute({
    'function': 'search_organizations',
    'name': 'Marine'
})

# Search by country
result = await execute({
    'function': 'search_organizations',
    'country': 'Switzerland'
})

# Combined search
result = await execute({
    'function': 'search_organizations',
    'name': 'Ocean',
    'country': 'France',
    'limit': '50'
})
```

### 3. `list_organizations`

List all organizations in the database.

**Parameters:**
- `existing_only` (optional, default "true"): Only return currently existing organizations
- `limit` (optional): Maximum number of results to return

**Example:**
```python
result = await execute({
    'function': 'list_organizations',
    'limit': '100'
})
```

### 4. `get_countries`

Get the complete mapping of country names to EDMO country codes.

**Example:**
```python
result = await execute({
    'function': 'get_countries'
})
```

## Return Data Structure

### Organization Detail (get_organization)

```json
{
  "success": true,
  "edmo_id": "4830",
  "url": "https://edmo.seadatanet.org/report/4830",
  "data": {
    "Name": "École Polytechnique Fédérale de Lausanne (EPFL)",
    "Native name": "Swiss Federal Institute of Technology in Lausanne",
    "Address": "Route Cantonale",
    "Zipcode": "1015",
    "City": "Lausanne",
    "Country": "Switzerland",
    "Phone": "+41216931111",
    "Centre Website": "https://www.epfl.ch/en/",
    "coordinates": {
      "latitude": 46.5202,
      "longitude": 6.567
    }
  },
  "services": [
    {
      "name": "Cruise summary report (CSR)",
      "url": "https://csr.seadatanet.org/edmo/4830"
    }
  ],
  "metadata": {
    "edmo_id": "4830",
    "title": "École Polytechnique Fédérale de Lausanne (EPFL) | SeaDataNet EDMO",
    "latest_update": "13 April 2026 12:44:05 PM"
  }
}
```

### Search Results (search_organizations, list_organizations)

```json
{
  "success": true,
  "count": 2,
  "records": [
    {
      "edmo_id": "4830",
      "name": "École Polytechnique Fédérale de Lausanne",
      "native_name": "Swiss Federal Institute of Technology in Lausanne",
      "abbreviation": "EPFL",
      "address": "Route Cantonale",
      "zipcode": "1015",
      "city": "Lausanne",
      "country": "Switzerland",
      "phone": "+41216931111",
      "website": "https://www.epfl.ch/en/",
      "url": "https://edmo.seadatanet.org/report/4830",
      "latitude": "46.5202",
      "longitude": "6.567"
    }
  ],
  "search_params": {
    "name": "EPFL",
    "country": null,
    "existing_only": true,
    "step_param": "003EPFL_0021"
  },
  "export_url": "https://edmo.seadatanet.org/v_edmo/browse_export.asp?step=003EPFL_0021"
}
```

## Data Fields

Each organization record typically contains:
- **edmo_id**: Unique EDMO identifier
- **name**: Organization name
- **native_name**: Organization name in native language
- **abbreviation**: Acronym or abbreviation
- **address**: Street address
- **address2**: Additional address information
- **zipcode**: Postal/ZIP code
- **city**: City
- **state**: State/Province
- **country**: Country name
- **email**: Contact email
- **phone**: Phone number
- **fax**: Fax number
- **website**: Organization website
- **url**: Direct EDMO record URL
- **latitude/longitude**: Geographic coordinates

## Technical Details

- **Base URL**: https://edmo.seadatanet.org
- **Export Format**: CSV (Windows-1252 encoding)
- **Rate Limiting**: Please use reasonable request rates
- **Timeout**: Default 30 seconds for individual requests, 60 seconds for exports

## Notes

- The `existing_only` parameter filters out organizations that have been merged, closed, or restructured
- Country codes in EDMO are numeric and can be obtained using the `get_countries` function
- Search supports partial name matching (e.g., "Marine" matches "Marine Biology Institute")
- Some organizations may have missing fields if the data is incomplete in the database
- The database contains over 5800 organizations worldwide

## Error Handling

All functions return a dictionary with:
- `success`: Boolean indicating if the operation succeeded
- `error`: Error message (only present if success is false)
- Additional fields with results (only present if success is true)