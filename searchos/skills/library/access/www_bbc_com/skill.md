# BBC Olympics Paris 2024 Medal Table

Access skill for fetching Olympic medal standings from BBC Sport.

## Overview

This skill retrieves the Paris 2024 Olympic medal table from BBC Sport's website. The data includes:
- Country rankings by gold medals
- Gold, silver, bronze, and total medal counts
- Country codes and names

## Functions

### get_medal_table

Retrieves the complete medal table with all participating countries.

**Example:**
```json
{
  "function": "get_medal_table"
}
```

**Response:**
```json
{
  "success": true,
  "function": "get_medal_table",
  "tournament": "paris-2024",
  "total_countries": 84,
  "medal_table": [
    {
      "rank": 1,
      "country_code": "US",
      "country_name": "United States",
      "gold": 40,
      "silver": 44,
      "bronze": 42,
      "total": 126
    },
    ...
  ]
}
```

### get_country_medals

Retrieves medal information for a specific country.

**Parameters:**
- `country_code` (optional): 3-letter country code (e.g., US, CHN, GB, JPN)
- `country_name` (optional): Full country name (e.g., "United States", "China")

**Example:**
```json
{
  "function": "get_country_medals",
  "country_code": "GB"
}
```

**Response:**
```json
{
  "success": true,
  "function": "get_country_medals",
  "country": {
    "code": "GB",
    "name": "Great Britain",
    "urn": "urn:bbc:sportsdata:olympics:country:great-britain"
  },
  "rank": 7,
  "medals": {
    "gold": 14,
    "silver": 22,
    "bronze": 29,
    "total": 65
  }
}
```

### get_top_countries

Retrieves the top N countries sorted by a specified medal metric.

**Parameters:**
- `limit` (optional): Number of countries to return (default: 10, max: 50)
- `sort_by` (optional): Medal type to sort by - "gold" (default), "silver", "bronze", or "total"

**Example:**
```json
{
  "function": "get_top_countries",
  "limit": 5,
  "sort_by": "total"
}
```

**Response:**
```json
{
  "success": true,
  "function": "get_top_countries",
  "sort_by": "total",
  "limit": 5,
  "countries": [
    {
      "rank": 1,
      "country_code": "US",
      "country_name": "United States",
      "gold": 40,
      "silver": 44,
      "bronze": 42,
      "total": 126
    },
    ...
  ]
}
```

## Data Source

The data is fetched from BBC Sport's Olympics page at:
`https://www.bbc.com/sport/olympics/paris-2024/medals`

After the 2024 Paris Olympics concluded, the medal table is now static and represents the final standings.

## Country Codes

Common country codes used in the medal table:
- **US** - United States
- **CHN** - China  
- **JPN** - Japan
- **AUS** - Australia
- **FRA** - France
- **NED** - Netherlands
- **GB** - Great Britain
- **KOR** - South Korea
- **ITA** - Italy
- **GER** - Germany

## Notes

- The medal table is sorted by gold medals by default (official IOC ranking)
- When countries have equal gold medals, they are sorted by silver, then bronze
- Countries with the same medal counts share the same rank position
- Data is cached in the page and does not change after the Olympics concluded