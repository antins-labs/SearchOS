# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Indie Arena Booth - Gamescom 2025 Games

This skill fetches game listings and detailed game information from the Indie Arena Booth at Gamescom 2025.

## Available Functions

### list_games

Lists all games exhibiting at Indie Arena Booth Gamescom 2025.

**Returns:**
- `count`: Total number of games
- `games`: Array of game objects with:
  - `id`: Unique game identifier (used for get_game)
  - `title`: Game title
  - `developer`: Developer name
  - `country`: Developer's country
  - `thumbnail`: Thumbnail image URL
  - `url`: Full URL to game detail page

**Example:**
```json
{
  "function": "list_games"
}
```

### get_game

Get detailed information about a specific game.

**Parameters:**
- `game_id` (required): The game's unique identifier

**Returns:**
- `game`: Detailed game object with:
  - `id`, `url`, `title`, `developer`
  - `platforms`: Array of platforms (Windows, Mac, etc.)
  - `genres`: Array of genre tags
  - `publisher`: Publisher name (if any)
  - `press_contact`: Object with `name`, `email`, `presskit` URL
  - `about_game`: Game description
  - `about_company`: Developer description
  - `screenshots`: Array of screenshot URLs
  - `videos`: Array of video URLs (YouTube)
  - `links`: Object with external links (Steam, YouTube, presskit, etc.)
  - `logos`: Array of logo image URLs

**Example:**
```json
{
  "function": "get_game",
  "game_id": "19001"
}
```

### search_games

Search for games by title or developer name (case-insensitive partial match).

**Parameters:**
- `query` (required): Search term

**Returns:**
- `query`: The search query
- `count`: Number of matching games
- `games`: Array of matching game objects (same format as list_games)

**Example:**
```json
{
  "function": "search_games",
  "query": "adventure"
}
```

## Data Source

All data is fetched from: https://indiearenabooth.de/gamescom2025/games

The Indie Arena Booth is a collective booth at Gamescom featuring indie game developers from around the world. Each game listing includes press kit information, screenshots, videos, and contact details for press inquiries.

## Notes

- Game IDs are numeric strings extracted from the URL structure
- The list contains approximately 197 games from Gamescom 2025
- Press contact information includes developer press kit URLs where available
- All screenshots and logos are hosted on indiearenabooth.de servers
