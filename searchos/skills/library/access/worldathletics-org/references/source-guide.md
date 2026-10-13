# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# World Athletics Rankings Access Skill

This skill fetches world athletics rankings data from [worldathletics.org](https://worldathletics.org).

## Features

- **Overall Rankings**: Get the overall world rankings for men or women
- **Event-Specific Rankings**: Get rankings for specific events (100m, marathon, high jump, etc.)
- **Region Filtering**: Filter by world, area (continent), or specific country
- **Age Category**: Filter by senior, U20, or U18 age groups
- **Pagination**: Supports fetching multiple pages of results

## Available Functions

### get_rankings

Get rankings for a specific event and gender.

**Parameters:**
- `event` (string): Event identifier (e.g., "overall", "100m", "marathon")
- `gender` (string): "men" or "women"
- `page` (integer): Starting page number (default: 1)
- `limit` (integer): Maximum number of results (default: 100)
- `region_type` (string): "world", "area", "country", or "country-group"
- `region` (string): Area name or country code when filtering by region
- `age_category` (string): "senior", "u20", or "u18"

**Example:**
```json
{
  "function": "get_rankings",
  "event": "1500m",
  "gender": "men",
  "limit": 10
}
```

**Returns:**
```json
{
  "success": true,
  "event": "1500m",
  "gender": "men",
  "count": 10,
  "rankings": [
    {
      "rank": 1,
      "athlete": "Cameron MYERS",
      "dob": "09 JUN 2006",
      "nationality": "AUS",
      "score": 1372,
      "events": "1500m [Mile,Mile sh]",
      "athlete_url": "https://worldathletics.org/athletes/australia/cameron-myers-14962470",
      "athlete_id": "..."
    }
  ]
}
```

### get_events

Get a list of all available events for querying.

**Example:**
```json
{
  "function": "get_events"
}
```

**Returns:**
```json
{
  "success": true,
  "count": 108,
  "events": [
    {
      "slug": "100-metres",
      "type": "sprints",
      "label": "100 Metres",
      "url_pattern": "/world-rankings/100-metres/{gender}"
    }
  ],
  "common_events": {
    "100m": "100-metres",
    "marathon": "marathon",
    ...
  }
}
```

### get_countries

Get a list of available countries for filtering.

**Example:**
```json
{
  "function": "get_countries"
}
```

## Common Event Slugs

| Short Name | Full Slug |
|------------|-----------|
| overall | overall-ranking |
| 100m | 100-metres |
| 200m | 200-metres |
| 400m | 400-metres |
| 800m | 800-metres |
| 1500m | 1500-metres |
| 5000m | 5000-metres |
| 10000m | 10000-metres |
| marathon | marathon |
| half-marathon | half-marathon |
| 110m-hurdles | 110-metres-hurdles |
| 400m-hurdles | 400-metres-hurdles |
| high-jump | high-jump |
| pole-vault | pole-vault |
| long-jump | long-jump |
| triple-jump | triple-jump |
| shot-put | shot-put |
| discus | discus-throw |
| hammer | hammer-throw |
| javelin | javelin-throw |
| decathlon | decathlon |
| heptathlon | heptathlon |

## Examples

### Get top 10 men's 100m rankings
```json
{
  "function": "get_rankings",
  "event": "100m",
  "gender": "men",
  "limit": 10
}
```

### Get women's marathon rankings for Europe
```json
{
  "function": "get_rankings",
  "event": "marathon",
  "gender": "women",
  "region_type": "area",
  "region": "europe"
}
```

### Get U20 men's 1500m rankings
```json
{
  "function": "get_rankings",
  "event": "1500m",
  "gender": "men",
  "age_category": "u20"
}
```

### Get second page of overall women's rankings
```json
{
  "function": "get_rankings",
  "event": "overall",
  "gender": "women",
  "page": 2
}
```

## Data Source

Data is fetched directly from World Athletics official website. Each ranking entry includes:
- Rank position
- Athlete name
- Date of birth
- Nationality
- Ranking score
- Associated events
- Link to athlete profile

## Notes

- Rankings are updated periodically by World Athletics
- Each page contains up to 100 athletes
- Region filtering uses World Athletics' official area and country codes
- Age category filtering defaults to Senior if not specified
