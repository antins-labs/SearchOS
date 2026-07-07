# Todor66.com Historical Volleyball Tournament Data Extractor

This skill extracts structured tournament data from todor66.com, a comprehensive archive of historical volleyball competition results including Olympic tournaments, World Championships, World Cups, and other international competitions.

## Capabilities

The skill can extract:

- **Tournament Metadata**: Title, year, dates, and winner
- **Finals Results**: Knockout stage matches with detailed set scores
- **Final Rankings**: Complete tournament standings with wins/losses
- **Group Stage**: Standings and match results from pool play
- **Team Rosters**: Player lineups when available in the page

## Supported URL Patterns

The skill works with various todor66.com volleyball pages:

```
http://www.todor66.com/volleyball/Other/Montreux_2005.html
http://www.todor66.com/volleyball/Olympics/Women/2004.html
http://www.todor66.com/volleyball/World/Women/2006.html
http://www.todor66.com/volleyball/World_Cup/Women/2007.html
```

## Functions

### get_tournament

Fetches and parses a complete tournament page, returning all available structured data.

**Parameters**:
- `url`: The tournament page URL

**Returns**:
```json
{
  "success": true,
  "data": {
    "metadata": {
      "title": "Women Volleyball XXI Montreux Volley Masters 2005 - 07-12.06 - Winner Brazil",
      "year": "2005",
      "dates": "07-12.06",
      "winner": "Brazil"
    },
    "finals_results": [
      {
        "round": "Final",
        "team1": "Brazil",
        "team2": "China",
        "score": "3-2",
        "sets_won_team1": 3,
        "sets_won_team2": 2,
        "set_scores": ["18-25", "24-26", "32-30", "25-15", "20-18"],
        "total_points": "119-114"
      }
    ],
    "final_rankings": [
      {"rank": 1, "team": "Brazil", "wins": 5, "losses": 0}
    ],
    "group_standings": {
      "A": [{"position": 1, "team": "China", "wins": 2, "losses": 1}]
    },
    "team_rosters": {
      "China": [
        {"number": "1", "name": "Wang Yimei"},
        {"number": "2", "name": "Feng Kun"}
      ]
    }
  }
}
```

### get_finals

Extracts only the finals/knockout stage results.

**Parameters**:
- `url`: The tournament page URL

### get_rankings

Extracts only the final tournament rankings.

**Parameters**:
- `url`: The tournament page URL

### get_groups

Extracts group stage standings and match results.

**Parameters**:
- `url`: The tournament page URL

### parse_html

Parses HTML content provided directly (no network request).

**Parameters**:
- `html`: Raw HTML content to parse
- `url`: Optional URL for reference

## Data Structure Notes

### Match Results

Each match includes:
- Round identifier (Final, 3-4, 1/2, 5-8)
- Date and time
- Teams and final set score
- Individual set scores
- Total points scored

### Rankings

Standings data includes:
- Final position
- Team name
- Win/loss record
- Point ratios (when available)

### Group Stage

Group data includes:
- Standings with wins/losses
- Individual match results
- Cross-group results matrix (when available)

## Technical Notes

- The site uses static HTML with no JavaScript/AJAX
- Data is embedded in table structures (sometimes nested)
- Encoding is plain ASCII/UTF-8
- No authentication or cookies required
- Rate limiting: Be respectful of the server