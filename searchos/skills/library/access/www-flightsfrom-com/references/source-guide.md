# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# FlightsFrom.com Access Skill

Retrieves flight route information from www.flightsfrom.com for any airport worldwide.

## Overview

This skill accesses www.flightsfrom.com to extract comprehensive flight route data, including:
- All direct destinations from an airport
- Airlines operating each route
- Flight frequencies and schedules
- Duration and pricing information
- Aircraft types used

## Functions

### get_airport_routes

Get complete route information for an airport.

**Parameters:**
- `airport_code` (required): 3-letter IATA code (e.g., 'JFK', 'LHR', 'HIA')
- `include_airlines` (optional, default: true): Include detailed airline data

**Example:**
```json
{
  "function": "get_airport_routes",
  "airport_code": "HIA"
}
```

**Returns:**
- Airport information (name, code, description)
- List of all destinations with:
  - Airport name, city, country
  - Flights per week/day
  - Flight duration
  - Operating days
  - Airlines serving the route
  - First/last flight dates
  - Starting price
- Summary with totals and countries served

### get_airport_info

Get basic airport information without full route details.

**Parameters:**
- `airport_code` (required): 3-letter IATA code

**Example:**
```json
{
  "function": "get_airport_info",
  "airport_code": "BPL"
}
```

**Returns:**
- Airport name and code
- Description
- Number of destinations
- Countries served
- List of destination codes

### search_destinations

Filter destinations by country or city.

**Parameters:**
- `airport_code` (required): Origin airport IATA code
- `country` (optional): Country name filter (partial match)
- `city` (optional): City name filter (partial match)

**Example:**
```json
{
  "function": "search_destinations",
  "airport_code": "HIA",
  "country": "China"
}
```

**Returns:**
- Matching destinations with full details

### get_route_details

Get details for a specific route between two airports.

**Parameters:**
- `from_airport` (required): Origin airport IATA code
- `to_airport` (required): Destination airport IATA code

**Example:**
```json
{
  "function": "get_route_details",
  "from_airport": "HIA",
  "to_airport": "SZX"
}
```

**Returns:**
- Route details including:
  - Flight frequency
  - Duration
  - Operating airlines
  - Aircraft types
  - Schedule information

## Data Fields

### Destination
| Field | Description |
|-------|-------------|
| iata_code | Destination airport IATA code |
| airport_name | Full airport name |
| city | City name |
| country | Country name |
| flights_per_week | Number of flights per week |
| flights_per_day | Flights per day description |
| duration_minutes | Average flight duration |
| operating_days | Days of operation (Mon-Sun) |
| airlines | List of airlines serving the route |
| price_from | Starting price (if available) |

### Airline
| Field | Description |
|-------|-------------|
| iata_code | Airline IATA code |
| name | Full airline name |
| country | Airline country |
| is_lowcost | Low-cost carrier flag |
| is_skyteam / is_staralliance / is_oneworld | Alliance membership |
| aircraft | Aircraft type codes |

## Notes

- Data is sourced from www.flightsfrom.com
- Route information includes scheduled flights up to 9 months ahead
- Prices are starting prices and may vary
- Some routes may be seasonal or have limited schedules
- The site uses Cloudflare protection; this skill uses appropriate headers to access the data
