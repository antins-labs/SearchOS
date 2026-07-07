# World Aquatics Access Skill

Access structured data from World Aquatics (formerly FINA) - the international governing body for aquatic sports.

## API Endpoints

**Base URL:** `https://api.worldaquatics.com/fina`

All requests require these headers:
```
Accept: application/json
Origin: https://www.worldaquatics.com
Referer: https://www.worldaquatics.com/
```

## Available Functions

### Athlete Functions

#### `get_athlete(athlete_id)`
Get athlete profile by ID.

**Example:**
```python
result = await execute({
    "function": "get_athlete",
    "athlete_id": 1001621  # Michael Phelps
})
# Returns: id, firstName, lastName, fullName, dateOfBirth, nationality, height, gender, disciplines
```

#### `get_athlete_medals(athlete_id)`
Get complete medal summary for an athlete.

**Example:**
```python
result = await execute({
    "function": "get_athlete_medals",
    "athlete_id": 1001621
})
# Returns: MedalsByEventType, MedalsByDiscipline, MedalsByEvent
# Total medals: MedalsByEventTypeTotalGold/Silver/Bronze/Total
```

Sample output for Michael Phelps:
- Total Gold: 85
- Total Silver: 21
- Total Bronze: 9

#### `get_athlete_results(athlete_id)`
Get complete competition results history.

**Example:**
```python
result = await execute({
    "function": "get_athlete_results",
    "athlete_id": 1001621
})
# Returns: FullName, Results[]
# Each result includes: CompetitionName, DisciplineName, Rank, MedalTag, Time, RecordType
```

#### `search_athletes(name, limit, page)`
Search athletes by name (last name or partial match).

**Example:**
```python
result = await execute({
    "function": "search_athletes",
    "name": "Phelps",  # Returns Michael Phelps, Whitney Phelps, Peter Phelps
    "limit": 10
})
```

### Competition Functions

#### `get_competition(competition_id)`
Get competition details by ID.

**Example:**
```python
result = await execute({
    "function": "get_competition",
    "competition_id": 816  # 10th FINA World Championships 2003
})
# Returns: id, name, officialName, dateFrom, dateTo, location, competitionType, disciplines
```

#### `get_competition_events(competition_id)`
Get full event structure with disciplines, rounds, and heats.

**Example:**
```python
result = await execute({
    "function": "get_competition_events",
    "competition_id": 816
})
# Returns: Sports[] with DisciplineList[]
# Each discipline has HeatList with heat IDs for results lookup
```

#### `get_competition_medals(competition_id)`
Get medal table for a competition.

**Example:**
```python
result = await execute({
    "function": "get_competition_medals",
    "competition_id": 816
})
# Returns: Medals.SportMedals[] with Countries[]
# Each country has Gold/Silver/Bronze counts and athlete details
```

**Sample output for 2003 World Championships:**
| Rank | Country | Gold | Silver | Bronze |
|------|---------|------|--------|--------|
| 1 | USA | 12 | 13 | 6 |
| 2 | Russia | 10 | 5 | 6 |
| 3 | Australia | 8 | 12 | 6 |

#### `list_competitions(limit, page)`
List all competitions.

**Example:**
```python
result = await execute({
    "function": "list_competitions",
    "limit": 20
})
# Returns: pageInfo, content[] with competition summaries
```

### Live Results

#### `get_live_results(date_from, date_to)`
Get live results for ongoing competitions.

**Example:**
```python
result = await execute({
    "function": "get_live_results",
    "date_from": "2024-02-01T00:00:00Z",
    "date_to": "2024-02-10T23:59:59Z"
})
```

## Data Reference

### Sport Codes
- `SW` - Swimming
- `DV` - Diving
- `SY` - Artistic Swimming (Synchronized Swimming)
- `WP` - Water Polo
- `OW` - Open Water Swimming
- `HD` - High Diving

### Medal Tags
- `G` - Gold
- `S` - Silver
- `B` - Bronze

### Record Types
- `WR` - World Record
- `OR` - Olympic Record
- `CR` - Championship Record

## Common Athlete IDs

| Athlete | ID |
|---------|-----|
| Michael Phelps (USA) | 1001621 |
| Katie Ledecky (USA) | 1002483 |
| Caeleb Dressel (USA) | 1036454 |
| Adam Peaty (GBR) | 1000785 |

## Common Competition IDs

| Competition | ID |
|-------------|-----|
| 10th FINA World Championships 2003 | 816 |
| Olympic Games Rio 2016 | 828 |
| Olympic Games Tokyo 2020 | 1016 |

## Example Usage

### Find athlete medals
```python
# Search for athlete
search = await execute({"function": "search_athletes", "name": "Phelps"})
athlete_id = search["data"]["content"][0]["id"]

# Get medals
medals = await execute({
    "function": "get_athlete_medals",
    "athlete_id": athlete_id
})

# Get results history
results = await execute({
    "function": "get_athlete_results",
    "athlete_id": athlete_id
})
```

### Get competition medal table
```python
# Get competition details
comp = await execute({
    "function": "get_competition",
    "competition_id": 816
})

# Get medal table
medals = await execute({
    "function": "get_competition_medals",
    "competition_id": 816
})

# Parse medal table
for sport in medals["data"]["Medals"]["SportMedals"]:
    for country in sport["Countries"][:5]:  # Top 5 countries
        print(f"{country['Rank']}. {country['CountryName']}: "
              f"G:{country['Gold']['Count']} "
              f"S:{country['Silver']['Count']} "
              f"B:{country['Bronze']['Count']}")
```

## Notes

- The API does not require authentication
- All timestamps are in UTC
- Pagination uses 0-based page indexing
- Some older competitions may have incomplete data
- Heat-level results are available via the events structure but require parsing heat IDs from get_competition_events
- Use search_athletes() to find athlete IDs by name before using other athlete functions