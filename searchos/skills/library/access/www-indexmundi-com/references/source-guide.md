# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# IndexMundi Country Profile Extractor

This skill extracts structured country profile data from IndexMundi, a comprehensive
factbook website that provides detailed statistics and information about countries
worldwide.

## Features

- **Reliable Extraction**: Parses the consistent table-based key-value layout used
  across all IndexMundi country profile pages
- **Multiple Profile Types**: Supports 11 different profile categories per country
- **No JavaScript Required**: Uses direct HTTP requests for fast, reliable fetching

## Supported Profile Types

| Profile Type | Description |
|--------------|-------------|
| `geography_profile` | Location, area, climate, terrain, natural resources |
| `demographics_profile` | Population, age structure, migration, literacy |
| `government_profile` | Government type, capital, political parties |
| `economy_profile` | GDP, unemployment, inflation, industries |
| `communications_profile` | Telephones, internet, broadcast media |
| `transportation_profile` | Airports, railways, roadways, ports |
| `military_profile` | Military branches, expenditures, service age |
| `energy_profile` | Electricity, oil, natural gas production/consumption |
| `environment_profile` | Pollution, climate agreements, natural hazards |
| `terrorism_profile` | Terrorist groups, incidents |
| `transnational_issues_profile` | Disputes, refugees, illicit drugs |

## Usage Examples

### Get Geography Profile

```json
{
  "function": "get_profile",
  "country": "canada"
}
```

Returns structured data with fields like:
- Location
- Geographic coordinates
- Area (total, land, water)
- Climate
- Terrain
- Natural resources
- And more...

### Get Specific Profile Type

```json
{
  "function": "get_profile",
  "country": "japan",
  "profile_type": "economy_profile"
}
```

### Get All Available Profiles

```json
{
  "function": "get_all_profiles",
  "country": "germany"
}
```

### Get Selected Profiles

```json
{
  "function": "get_all_profiles",
  "country": "australia",
  "profile_types": ["geography_profile", "demographics_profile", "economy_profile"]
}
```

### List Available Profile Types

```json
{
  "function": "list_profile_types"
}
```

## Country Name Format

The skill accepts various country name formats and normalizes them automatically:
- `canada` → canada
- `United States` → united_states  
- `united-states` → united_states
- `SOUTH_AFRICA` → south_africa

## Output Structure

### get_profile Response

```json
{
  "success": true,
  "country": "canada",
  "profile_type": "geography_profile",
  "url": "https://www.indexmundi.com/canada/geography_profile.html",
  "data": {
    "title": "Canada Geography Profile",
    "fields": {
      "Location": "Northern North America, bordering...",
      "Geographic coordinates": "60 00 N, 95 00 W",
      "Area": "total: 9,984,670 sq km..."
    },
    "raw_fields": [
      {"key": "Location", "value": "Northern North America..."},
      {"key": "Geographic coordinates", "value": "60 00 N, 95 00 W"}
    ]
  }
}
```

### get_all_profiles Response

```json
{
  "success": true,
  "country": "canada",
  "profiles": {
    "geography_profile": {...},
    "demographics_profile": {...},
    ...
  },
  "successful": ["geography_profile", "demographics_profile", ...],
  "failed": [],
  "total_profiles": 11
}
```

## Error Handling

The skill returns structured error responses rather than raising exceptions:

```json
{
  "success": false,
  "error": "Profile not found for country 'invalid_country'",
  "status_code": 404
}
```

## Data Source

Data is sourced from IndexMundi (www.indexmundi.com), which compiles information
from various public domain sources including the CIA World Factbook.
