# FIS-SKI.com Database Access Skill

Access the official FIS (International Ski Federation) database for athlete biographies and competition results.

## Overview

This skill provides programmatic access to the authoritative database for international skiing competitions maintained by the FIS (Fédération Internationale de Ski). It covers multiple skiing disciplines including:

- **Freestyle Skiing (FS)** - Moguls, aerials, halfpipe, slopestyle, big air
- **Alpine Skiing (AL)** - Downhill, super-G, giant slalom, slalom
- **Snowboarding (SB)** - Halfpipe, slopestyle, cross, alpine
- **Cross-Country (CC)** - Sprint, distance, relay
- **Ski Jumping (JP)** - Individual, team events
- **Nordic Combined (NC)** - Combined cross-country and ski jumping

## Functions

### get_athlete_bio

Retrieve an athlete's biography and complete competition history.

**Parameters:**
- `competitorid` (required): FIS competitor ID (e.g., "226193")
- `sectorcode` (optional): Sport sector code, defaults to "fs"
- `type` (optional): Result type, defaults to "result"

**Returns:**
- Profile information (name, country, team, birthdate, FIS code, etc.)
- List of competition results with dates, venues, positions, and points

**Example:**
```python
result = await execute({
    "function": "get_athlete_bio",
    "competitorid": "226193",
    "sectorcode": "fs"
})
```

**Response Structure:**
```json
{
  "success": true,
  "profile": {
    "firstname": "Ailing Eileen",
    "lastname": "GU",
    "fullname": "Ailing Eileen GU",
    "country_code": "CHN",
    "country_name": "P.r. China",
    "team": "Beijing Nanshan Ski Resort",
    "fis_code": 2534563,
    "birthdate": "03-09-2003",
    "image_url": "https://data.fis-ski.com/general/load-competitor-picture/226193.html"
  },
  "results": [
    {
      "date": "22-02-2026",
      "place": "Livigno",
      "nation_code": "ITA",
      "category": "OWG",
      "discipline": "Freeski Halfpipe",
      "position": "1",
      "fis_points": "1000.00",
      "raceid": "19025"
    }
  ]
}
```

### get_race_results

Retrieve detailed results for a specific race/competition.

**Parameters:**
- `raceid` (required): FIS race ID (e.g., "19025")
- `sectorcode` (optional): Sport sector code, defaults to "FS"
- `competitorid` (optional): Competitor ID for context

**Returns:**
- Event information (venue, season)
- Complete start list with rankings, scores, and FIS points

**Example:**
```python
result = await execute({
    "function": "get_race_results",
    "raceid": "19025",
    "sectorcode": "FS"
})
```

**Response Structure:**
```json
{
  "success": true,
  "venue": "Livigno (ITA)",
  "event": "Freestyle Results - Milano Cortina (ITA)",
  "season": "2025/2026",
  "results": [
    {
      "rank": 1,
      "bib": "2",
      "fis_code": "2534563",
      "competitorid": "226193",
      "athlete": "GU Ailing Eileen",
      "birth_year": 2003,
      "nation": "CHN",
      "score": 94.75,
      "fis_points": 1000.0
    }
  ]
}
```

## Finding IDs

### Competitor ID
1. Visit the athlete's biography page on fis-ski.com
2. The URL contains the competitorid parameter
3. Example: `https://www.fis-ski.com/DB/general/athlete-biography.html?competitorid=226193`

### Race ID
1. Visit any competition results page on fis-ski.com
2. The URL contains the raceid parameter
3. Example: `https://www.fis-ski.com/DB/general/results.html?raceid=19025`

### Sector Codes
- `fs` - Freestyle Skiing
- `al` - Alpine Skiing
- `sb` - Snowboarding
- `cc` - Cross-Country
- `jp` - Ski Jumping
- `nc` - Nordic Combined

## Technical Details

### Data Source
The FIS database uses server-side rendered HTML pages (Next.js framework) rather than a public JSON API. This skill parses the HTML to extract structured data.

### Categories
Common event categories you may encounter:
- **OWG** - Olympic Winter Games
- **WC** - World Cup
- **WCH** - World Championships
- **JC** - Junior Competitions
- **NC** - Nor-Am Cup, European Cup, etc.

### Error Handling
The skill returns structured error responses:
```json
{
  "success": false,
  "error": "Missing required parameter: competitorid",
  "error_type": "validation"
}
```

Error types:
- `validation` - Invalid or missing parameters
- `network` - Failed to fetch data from FIS website
- `parse` - Failed to parse response (unexpected format)

## Use Cases

1. **Athlete Research**: Get complete competition history for any FIS-registered athlete
2. **Competition Analysis**: Analyze race results and rankings
3. **Historical Data**: Access past competition results and athlete performance
4. **Data Integration**: Incorporate official FIS data into applications

## Limitations

- Data is sourced from public FIS website pages
- No real-time updates; data reflects what's published on the website
- Rate limiting may apply; implement appropriate request delays
- Some historical data may have limited availability

## Example Workflow

```python
# Get athlete profile
athlete = await execute({
    "function": "get_athlete_bio",
    "competitorid": "226193"
})

if athlete["success"]:
    print(f"Athlete: {athlete['profile']['fullname']}")
    print(f"Country: {athlete['profile']['country_name']}")
    print(f"Results: {len(athlete['results'])} competitions")
    
    # Get details of most recent race
    if athlete['results']:
        latest = athlete['results'][0]
        race = await execute({
            "function": "get_race_results",
            "raceid": latest['raceid']
        })
        
        if race["success"]:
            print(f"Race venue: {race['venue']}")
            print(f"Participants: {len(race['results'])}")
```

## Data Freshness

The FIS database is updated regularly with:
- Competition results (typically within hours of event completion)
- Standings and rankings
- Athlete registration updates
- Schedule information

For the most current data, always fetch directly from the live service.