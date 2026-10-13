# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# KOF Wiki Access Skill

This skill retrieves structured information about King of Fighters (KOF) characters, bosses, teams, and games from the KOF Wiki at kof.fandom.com.

## Features

### Boss Information
- **get_bosses**: Retrieve all bosses organized by saga
  - Optional `saga` parameter to filter by story arc (Rugal, Orochi, NESTS, Ash, Maximum Impact)
  - Returns boss name, description, saga, and link to full page

### Character Information
- **get_characters**: Get a list of all characters in the wiki
  - Optional `limit` parameter to control result count
  - Returns character names with links to their pages

- **get_character**: Get detailed information about a specific character
  - Requires `name` parameter
  - Returns description, story, personality, powers, fighting style, game appearances, and related links

### Team Information
- **get_teams**: Get a list of all teams
  - Returns team names with links

- **get_team**: Get detailed information about a specific team
  - Requires `name` parameter
  - Returns description, members, and related characters

### Search and General Pages
- **search**: Search the wiki for pages matching a query
  - Requires `query` parameter
  - Optional `limit` parameter

- **get_page**: Get content from any wiki page
  - Requires `title` parameter
  - Returns sections, headings, content paragraphs, and links

## Usage Examples

### Get all bosses
```
function: get_bosses
```

### Get bosses from NESTS saga
```
function: get_bosses
saga: NESTS
```

### Get character details
```
function: get_character
name: Rugal Bernstein
```

### Get team information
```
function: get_team
name: Fatal Fury Team
```

### Search for pages
```
function: search
query: Orochi
```

### Get a specific wiki page
```
function: get_page
title: The King of Fighters '94
```

## Data Source

All data is retrieved from the KOF Wiki MediaWiki API at kof.fandom.com. The wiki contains comprehensive information about:
- Over 200 characters from the KOF series
- Boss characters organized by story saga
- Team compositions and histories
- Game appearances and storylines

## Notes

- The KOF Wiki uses interwiki links for some popular characters (like Kyo Kusanagi, Iori Yagami) which may redirect to the main SNK wiki. These pages may return limited information.
- Character pages include detailed sections on story, personality, powers, fighting style, and game appearances.
- Boss information is extracted from the consolidated "Boss" page which organizes bosses by story saga.
