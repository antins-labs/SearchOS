# StatMuse FC Statistics Access Skill

This skill fetches football (soccer) statistics from StatMuse's FC section at `www.statmuse.com/fc`. It parses HTML table data returned by natural language queries.

## Features

- **Natural Language Queries**: Ask questions like "premier league top scorers 2023-24" or "most sofascore rating in la liga 2022-23"
- **Player Statistics**: Search for player stats by league, season, and stat type
- **League Standings**: Get current or historical league tables
- **Head-to-Head**: View match history between two teams

## Available Functions

### ask

Ask a natural language question to StatMuse FC.

**Parameters:**
- `query` (required): Natural language question
- `format` (optional): Output format - 'first_table' (default), 'full', or 'text'

**Examples:**
- `"premier league top scorers 2023-24"` - Top goal scorers
- `"highest rated players la liga 2022-23"` - Best player ratings
- `"real madrid vs barcelona 2023"` - Match history
- `"manchester city 2023-24 stats"` - Team statistics

### search_player_stats

Search for player statistics with structured parameters.

**Parameters:**
- `player` (optional): Player name
- `league` (optional): League name (e.g., "premier league", "la liga")
- `season` (optional): Season string (e.g., "2023-24")
- `stat` (optional): Stat to search for ("goals", "assists", "rating")
- `club` (optional): Club/team name
- `limit` (optional): Max results (default 25)

### get_standings

Get league standings/table.

**Parameters:**
- `league` (required): League name
- `season` (optional): Season string

### head_to_head

Get head-to-head match history between two teams.

**Parameters:**
- `team1` (required): First team name
- `team2` (required): Second team name
- `season` (optional): Season string

## Response Format

All functions return structured data:
- `error`: null if success, error code if failed
- `message`: Error description if applicable
- `headers`: Column headers for the data table
- `rows`: Array of data rows (each row is an array of values)
- `row_count`: Number of data rows
- `text`: Plain text table representation

## Notes

- Some queries may return "query not understood" if StatMuse doesn't recognize the format
- Queries typically return multiple related tables (e.g., standings from multiple leagues)
- Use `format: 'full'` in the ask function to get all tables
- Stats include Sofascore ratings, goals, assists, appearances, minutes, and more

## Supported Leagues

- Premier League
- La Liga (LaLiga)
- Bundesliga
- Serie A
- Ligue 1
- Champions League
- And more...

## Example Queries

```python
# Top scorers in Premier League
execute({'function': 'ask', 'query': 'premier league top scorers 2023-24'})

# Highest rated La Liga players
execute({'function': 'search_player_stats', 'league': 'la liga', 'season': '2022-23', 'stat': 'rating'})

# Premier League standings
execute({'function': 'get_standings', 'league': 'premier league', 'season': '2023-24'})

# Real Madrid vs Barcelona
execute({'function': 'head_to_head', 'team1': 'real madrid', 'team2': 'barcelona', 'season': '2023'})
```