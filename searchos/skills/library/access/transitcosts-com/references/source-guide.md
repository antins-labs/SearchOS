# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Transit Costs Project Access Skill

This skill retrieves structured data from the [Transit Costs Project](https://transitcosts.com) database, which contains detailed information about transit infrastructure projects worldwide.

## Available Functions

### `get_project`

Get detailed information for a specific transit project by URL.

**Parameters:**
- `url` (required): The project page URL from transitcosts.com

**Example:**
```json
{
  "function": "get_project",
  "url": "https://transitcosts.com/hongkong-eastern-harbour-crossing/"
}
```

**Returns:**
- Project info: name, country, city, regional rail status
- Construction details: start/end year, length, tunnel percentage, stations
- Cost information: cost in original currency, PPP rate, real cost in USD, cost per km
- Reference URL and notes

### `list_projects`

List all transit projects in the database with optional filters.

**Parameters:**
- `city` (optional): Filter by city name
- `country` (optional): Filter by country code (e.g., "US", "CN", "UK")
- `limit` (optional): Maximum results to return (default: 50)

**Example:**
```json
{
  "function": "list_projects",
  "country": "US",
  "limit": 20
}
```

### `search_projects`

Search for projects by name with optional filters.

**Parameters:**
- `query` (required): Search term for project name
- `city` (optional): Filter by city name
- `country` (optional): Filter by country code
- `limit` (optional): Maximum results to return (default: 50)

**Example:**
```json
{
  "function": "search_projects",
  "query": "subway",
  "city": "New York"
}
```

## Data Fields

### Project Information
- `name`: Transit line name
- `country`: Country code
- `city`: City name
- `regional_rail`: Whether the line is regional rail (Yes/No)

### Construction Details
- `start_year`: Construction start year
- `end_year`: Construction end year
- `length_km`: Total corridor length in kilometers
- `tunnel_km`: Tunnel length in kilometers
- `tunnel_percentage`: Percentage of line that is tunneled
- `stations`: Number of stations
- `source`: Data source type (Plan, Trade, etc.)

### Cost Information
- `cost_millions`: Original cost in millions (local currency)
- `currency`: Original currency
- `ppp_rate`: Purchasing power parity rate used
- `ppp_year`: Year of PPP rate
- `real_cost_millions_usd`: Cost adjusted to USD using PPP
- `cost_per_km_millions_usd`: Cost per kilometer in millions USD
- `source`: Cost data source

## Notes

- The Transit Costs Project includes data from over 600 transit projects worldwide
- Costs are adjusted for purchasing power parity (PPP) based on the midpoint of construction
- Costs include construction and construction-related expenditures, but not rolling stock or sales taxes
- Length refers to corridor length, not total single-track length
- For more information, visit the [Transit Costs Project data page](https://transitcosts.com/data/)
