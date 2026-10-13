# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Game of Thrones Fandom Wiki Access Skill

This skill fetches structured information from the Game of Thrones Fandom wiki (gameofthrones.fandom.com) using the MediaWiki API. It reliably parses infobox data that generic web readers often fail to extract properly.

## Features

- **Reliable API Access**: Uses the MediaWiki API to bypass Cloudflare protection and get structured data
- **Infobox Parsing**: Extracts and cleans wikitext infobox data for characters, episodes, houses, locations, and more
- **Multiple Entity Types**: Specialized functions for different wiki page types
- **Section Extraction**: Can retrieve specific sections from long wiki pages

## Available Functions

### `get_page`
Get complete information about any wiki page including:
- Title and URL
- Infobox type and parsed data
- Page categories
- Table of contents (sections)
- Introduction text

Parameters:
- `title` (required): Page title (e.g., "Sansa Stark", "The Iron Throne")

### `search`
Search for wiki pages matching a query.

Parameters:
- `query` (required): Search terms
- `limit` (optional): Maximum results (default: 10)

### `get_character`
Get detailed character information including:
- Name, image, birth/death
- House affiliation
- Titles and aliases
- Family relations (parents, spouse, siblings)
- Actor who played the character
- Episode appearances

Parameters:
- `name` (required): Character name

### `get_episode`
Get detailed episode information including:
- Season and episode number
- Air date and runtime
- Writer and director
- Previous/next episode links

Parameters:
- `title` (required): Episode title

### `get_house`
Get detailed house/noble family information including:
- Coat of arms and words (motto)
- Seat and region
- Current head and heir
- Founding and history

Parameters:
- `name` (required): House name (e.g., "House Stark", "House Lannister")

### `get_section`
Get the content of a specific section from a wiki page.

Parameters:
- `title` (required): Page title
- `section` (required): Section name

## Example Usage

```json
// Get character info
{"function": "get_character", "name": "Sansa Stark"}

// Get episode info
{"function": "get_episode", "title": "The Iron Throne"}

// Get house info
{"function": "get_house", "name": "House Stark"}

// Search for pages
{"function": "search", "query": "White Walkers", "limit": 5}

// Get specific section
{"function": "get_section", "title": "Jon Snow", "section": "Biography"}
```

## Supported Infobox Types

- **Character**: People in the Game of Thrones universe
- **Episode**: TV series episodes
- **House**: Noble families and dynasties
- **Location**: Places and landmarks
- **Battle**: Military conflicts
- **Event**: Historical events
- **Creature**: Animals and mythical beings
- **Organization**: Groups and orders

## Notes

- The skill uses the MediaWiki API directly, which is more reliable than web scraping
- Wikitext markup is cleaned from all returned values
- For characters, the function will attempt to find the correct page if the name doesn't match exactly
- All text is returned in plain text format with wiki links resolved
