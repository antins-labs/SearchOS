# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Track & Field News Rankings Access Skill

This skill fetches world and U.S. track & field rankings from Track & Field News (trackandfieldnews.com).

## Features

### get_article
Fetches a specific ranking article and extracts structured data including:
- **World Rankings**: Complete list of ranked athletes with their performance history
  - Athlete name, country, date of birth
  - Detailed performance list including times, meet placements, dates, and notes
- **U.S. Rankings**: American athlete rankings (when present in article)
- **Article Introduction**: Context and analysis text

Example URL: `https://trackandfieldnews.com/article/2025-mens-1500-world-rankings/`

### get_index
Fetches the rankings index page showing all available events with links to their rankings.

Supported events include:
- Track: 100m, 200m, 400m, 800m, 1500m/Mile, Steeplechase, 5000m, 10,000m, Hurdles
- Road: Marathon, Race Walks
- Field: High Jump, Pole Vault, Long Jump, Triple Jump, Shot Put, Discus, Hammer, Javelin
- Combined: Decathlon/Heptathlon

## Data Structure

### World Rankings Entry
```json
{
  "rank": 1,
  "athlete": "NIELS LAROS",
  "country": "Netherlands",
  "dob": "4/17/05",
  "performances": [
    {
      "time": "3:29.20",
      "place": "1)Zürich DL",
      "date": "8/28"
    }
  ]
}
```

### U.S. Rankings Entry
```json
{
  "rank": 1,
  "athlete": "Yared Nuguse",
  "team": "On AC",
  "performances": [
    {
      "place": "2)",
      "meet": "Eugene DL"
    }
  ]
}
```

## Usage Notes

- The site provides detailed ranking articles with performance history and analysis
- Most historical rankings are available as PDF files linked from the index pages
- Article URLs follow the pattern: `/article/{year}-{gender}s-{event}-world-rankings/`
- Rankings are updated annually after each track season
