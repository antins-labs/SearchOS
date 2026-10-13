# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Volleyball World Competition Data Access Skill

This skill fetches structured competition data from en.volleyballworld.com for FIVB volleyball tournaments.

## Supported Competitions

- **Volleyball Challenger Cup** (2023, 2024)
  - Men's and Women's tournaments

## Available Functions

### 1. list_competitions
Lists all available competitions with their tournament numbers and supported years.

```python
execute({"function": "list_competitions"}, ctx)
```

### 2. tournament_info
Get basic information about a tournament including name, location, dates, and team count.

```python
execute({
    "function": "tournament_info",
    "competition": "challenger-cup",
    "year": "2024",
    "gender": "men"
}, ctx)
```

### 3. teams
Get all teams participating in a tournament.

```python
execute({
    "function": "teams",
    "competition": "challenger-cup",
    "year": "2024",
    "gender": "women"
}, ctx)
```

### 4. matches
Get all matches with scores and results.

```python
execute({
    "function": "matches",
    "competition": "challenger-cup",
    "year": "2023",
    "gender": "men"
}, ctx)
```

### 5. standings
Get final standings/rankings for a tournament.

```python
execute({
    "function": "standings",
    "competition": "challenger-cup",
    "year": "2023",
    "gender": "women"
}, ctx)
```

## Data Sources

The skill uses Volleyball World's internal APIs:
- Tournament data API: `/api/v1/volley-tournament/{startDate}/{endDate}/{tournamentNo}`
- Bracket data API: `/api/brackets/volley/{slug}/{tournamentNo}/{startDate}/{endDate}`

## Known Tournament Numbers

| Competition | Year | Gender | Tournament No | Dates |
|-------------|------|--------|---------------|-------|
| Challenger Cup | 2023 | Men | 1347 | Jul 27-30 |
| Challenger Cup | 2023 | Women | 1346 | Jul 27-30 |
| Challenger Cup | 2024 | Men | 1441 | Jul 4-7 |
| Challenger Cup | 2024 | Women | 1442 | Jul 4-7 |

## Output Format

### Match Data
```json
{
  "match_no": 20196,
  "date_utc": "2024-07-04T07:30:00Z",
  "team_a": {"name": "China", "code": "CHN", "score": 3},
  "team_b": {"name": "Mexico", "code": "MEX", "score": 0},
  "winner": "China",
  "sets": [...],
  "round": "Final Round",
  "pool": "Quarter-finals"
}
```

### Team Data
```json
{
  "name": "China",
  "code": "CHN",
  "country": "China",
  "no": 7007,
  "flag_url": "https://images.volleyballworld.com/..."
}
```

## Notes

- The API requires exact tournament numbers and date ranges
- Match status: 2 = completed, 1 = in progress, 0 = scheduled
- Set scores use 0-based indexing (set 0 = first set in some responses)
- The skill handles both the new tournament API (2024+) and bracket API (2023)
