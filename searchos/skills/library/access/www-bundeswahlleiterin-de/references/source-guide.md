# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Bundeswahlleiterin.de Election Results Access Skill

This skill retrieves German federal election (Bundestag) results from the official website of the Federal Returning Officer (Bundeswahlleiterin.de).

## Overview

The German Federal Returning Officer website provides comprehensive election data including:
- National-level results for all of Germany
- State-level (Länder) results for each of the 16 German states
- Detailed party vote counts and percentages
- Seat distribution in the Bundestag
- Press releases with final results

## Available Functions

### get_national_results

Retrieves national election results for Germany.

**Parameters:**
- `election_year`: Election year (default: "2025")

**Returns:**
- Seat distribution by party with changes from previous election
- Vote statistics (eligible voters, turnout, invalid/valid votes)
- Party results with first votes (Erststimmen) and second votes (Zweitstimmen)
- Percentages and changes from previous election

**Example:**
```python
params = {
    "function": "get_national_results",
    "election_year": "2025"
}
```

### get_state_results

Retrieves election results for a specific German state.

**Parameters:**
- `election_year`: Election year (default: "2025")
- `state`: State name or code (required)

**Valid state names:**
- schleswig-holstein (1)
- hamburg (2)
- niedersachsen (3)
- bremen (4)
- nordrhein-westfalen (5)
- hessen (6)
- rheinland-pfalz (7)
- baden-wuerttemberg (8)
- bayern (9)
- saarland (10)
- berlin (11)
- brandenburg (12)
- mecklenburg-vorpommern (13)
- sachsen (14)
- sachsen-anhalt (15)
- thueringen (16)

**Example:**
```python
params = {
    "function": "get_state_results",
    "election_year": "2025",
    "state": "bayern"  # or "9"
}
```

### get_press_release

Fetches a specific press release page with election results.

**Parameters:**
- `url`: Full URL or relative path to the press release

**Example:**
```python
params = {
    "function": "get_press_release",
    "url": "https://www.bundeswahlleiterin.de/en/info/presse/mitteilungen/bundestagswahl-2025/29_25_endgueltiges-ergebnis.html"
}
```

### list_states

Lists all available German states with their codes.

**Parameters:**
- `election_year`: Election year (default: "2025")

**Example:**
```python
params = {
    "function": "list_states"
}
```

### list_years

Attempts to list available election years from the website.

**Example:**
```python
params = {
    "function": "list_years"
}
```

## Data Structure

### National Results
```json
{
  "title": "Results Germany - The Federal Returning Officer",
  "level": "national",
  "election_year": "2025",
  "seat_distribution": {
    "data": [
      {"party": "SPD", "seats": "120", "change_from_2021": "-86"},
      {"party": "CDU", "seats": "164", "change_from_2021": "+12"}
    ]
  },
  "vote_statistics": {
    "data": [
      {
        "metric": "Voters",
        "first_votes": {"number": "49,928,653", "percent": "82.5", "change": "+6.2"},
        "second_votes": {"number": "49,928,653", "percent": "82.5", "change": "+6.2"}
      }
    ]
  },
  "party_results": [
    {
      "party": "SPD",
      "first_votes": {"number": "9,936,433", "percent": "20.1", "change": "-6.3"},
      "second_votes": {"number": "8,149,124", "percent": "16.4", "change": "-9.3"}
    }
  ]
}
```

## Notes

- The website uses HTML tables for data presentation, which are parsed and structured
- First votes (Erststimmen) determine constituency winners
- Second votes (Zweitstimmen) determine overall seat distribution
- The site provides both current results and comparisons with previous elections
- Party names use German abbreviations (SPD, CDU, CSU, AfD, Grüne, etc.)
