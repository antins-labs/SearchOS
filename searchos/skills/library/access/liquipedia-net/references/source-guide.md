# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Liquipedia Dota 2 Tournament Data Access Skill

This skill extracts structured tournament information from Liquipedia.net Dota 2 wiki pages.

## Supported Functions

### get_tournament_info
Extracts basic tournament information from the infobox, including:
- Series name
- Organizer(s)
- Event type (Offline/Online)
- Location and venue
- Format description
- Prize pool amount
- Start and end dates
- Game version
- Number of teams
- Liquipedia tier

**Example:**
```json
{
  "function": "get_tournament_info",
  "url": "https://liquipedia.net/dota2/The_International/2011"
}
```

### get_prize_pool
Extracts the prize pool distribution table, showing placement, team name, prize money, and percentage for each position.

**Example:**
```json
{
  "function": "get_prize_pool",
  "url": "https://liquipedia.net/dota2/The_International/2021"
}
```

### get_group_standings
Extracts group stage standings with team rankings, names, and win-loss records.

**Example:**
```json
{
  "function": "get_group_standings",
  "url": "https://liquipedia.net/dota2/The_International/2011"
}
```

### get_all_data
Extracts all available tournament data in a single call, including tournament info, prize pool, group standings, and match results.

**Example:**
```json
{
  "function": "get_all_data",
  "url": "https://liquipedia.net/dota2/The_International/2021"
}
```

## Data Structure

### Tournament Info Response
```json
{
  "page_title": "The International 2021 - Liquipedia Dota 2 Wiki",
  "tournament_info": {
    "Series": "The International",
    "Organizers": "Valve, PGL",
    "Type": "Offline",
    "Location": "Bucharest",
    "Venue": "Arena Naţională",
    "Prize Pool": "$40,018,195 USD",
    "Start Date": "2021-10-07",
    "End Date": "2021-10-17"
  }
}
```

### Prize Pool Response
```json
{
  "prize_pool": [
    {
      "place": "1",
      "team": "Team Spirit",
      "prize": "$18,208,300",
      "percent": "45.5%"
    },
    {
      "place": "2",
      "team": "PSG.LGD",
      "prize": "$5,202,400",
      "percent": "13%"
    }
  ]
}
```

### Group Standings Response
```json
{
  "groups": [
    {
      "group_name": "Group A",
      "standings": [
        {
          "rank": "1.",
          "team": "EHOME",
          "record": "3-0"
        },
        {
          "rank": "2.",
          "team": "Invictus Gaming",
          "record": "2-1"
        }
      ]
    }
  ]
}
```

## Notes

- The skill uses browser automation to render JavaScript-heavy pages
- Pages may take several seconds to load due to dynamic content
- The skill handles Liquipedia's specific table and infobox structures
- Error responses include descriptive messages for troubleshooting

## Supported Tournaments

This skill works with any Dota 2 tournament page on Liquipedia.net, including:
- The International (all years)
- Major tournaments
- Minor tournaments
- Regional leagues
- Custom tournament pages with standard Liquipedia formatting
