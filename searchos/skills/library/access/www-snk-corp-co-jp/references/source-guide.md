# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# SNK KOF XIV Access Skill

This skill retrieves data from the official SNK Corporation website for THE KING OF FIGHTERS XIV game.

## Overview

The KOF XIV official website uses JavaScript for dynamic content loading, which means standard HTTP requests return "Now Loading" placeholders. This skill uses Playwright browser automation to properly render and extract the content.

## Available Functions

### get_character

Fetches detailed profile information for a specific character.

**Parameters:**
- `character` (string, required): Character name or ID

**Known Characters:**
- kusanagi (Kyo Kusanagi)
- benimaru (Benimaru Nikaido)
- daimon (Goro Daimon)
- antonov
- verse

**Example:**
```json
{
  "function": "get_character",
  "character": "verse"
}
```

**Returns:**
- Character profile information (fighting style, birthdate, hobbies, etc.)
- Voice actor information
- Page content and text

### get_team

Fetches information about a specific team and its members.

**Parameters:**
- `team` (string, required): Team name or ID

**Known Teams:**
- japan (Japan Team)
- officialinvi (Official Invitation Team)
- southamerica (South America Team)
- yagami (Yagami Team)
- kim (Kim Team)
- mexico (Mexico Team)
- another (Another World Team)
- villains (Villains Team)
- china (China Team)
- kdash (K' Team)
- ikari (Ikari Team)
- southtown (South Town Team)
- fatalfury (Fatal Fury Team)
- women (Women Fighters Team)
- psychosoldier (Psycho Soldier Team)
- artoffighting (Art of Fighting Team)

**Example:**
```json
{
  "function": "get_team",
  "team": "japan"
}
```

**Returns:**
- Team name
- List of team members with links to their profiles
- Team description text

### list_teams

Lists all available teams in KOF XIV.

**Parameters:** None

**Example:**
```json
{
  "function": "list_teams"
}
```

**Returns:**
- List of all teams with names, IDs, and URLs

### get_story

Fetches the game's story information.

**Parameters:** None

**Example:**
```json
{
  "function": "get_story"
}
```

**Returns:**
- Story page content and text

## Technical Notes

- The website uses JavaScript for content loading, requiring browser automation
- Playwright is used with Chromium in headless mode
- Pages may load slowly; timeouts are handled gracefully
- Character and team IDs are derived from the URL structure (e.g., `/characters/verse.php`)

## Error Handling

All functions return a structured response with:
- `success`: boolean indicating if the operation succeeded
- `error`: error message if success is false
- Additional data fields on success

Common errors:
- Missing required parameters
- Unknown character/team (will attempt to construct URL from provided name)
- Page load timeout (partial content may still be available)
