# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Steam Store Access Skill

This skill retrieves structured information from Steam Store pages at store.steampowered.com.

## Capabilities

- **Single App Details**: Fetch comprehensive information about a specific Steam app including:
  - Title and description
  - Price (regular, discounted, or free)
  - Release date
  - Developer and publisher
  - User review summary and count
  - Metacritic score
  - Platforms (Windows, macOS, Linux)
  - Tags and genres
  - DLC information
  - System requirements
  - Screenshots and trailer availability

- **Multiple Apps**: Batch fetch details for multiple Steam apps in a single request

- **Search**: Search Steam catalog by keywords and return matching apps with basic info

## Usage Examples

### Get App Details by App ID

```json
{
  "function": "get_app_details",
  "appid": "1670540"
}
```

### Get App Details by URL

```json
{
  "function": "get_app_details",
  "url": "https://store.steampowered.com/app/2325832/Total_War_WARHAMMER_III__Elspeth__Thrones_of_Decay/"
}
```

### Get Multiple Apps

```json
{
  "function": "get_multiple_apps",
  "appids": ["1670540", "2325832", "1145360"]
}
```

### Search for Apps

```json
{
  "function": "search_apps",
  "query": "Total War Warhammer",
  "count": 10
}
```

## Output Structure

### App Details Response

```json
{
  "success": true,
  "appid": "1670540",
  "title": "Total War: WARHAMMER III - Ogre Kingdoms",
  "short_description": "...",
  "description": "...",
  "release_date": "Feb 24, 2022",
  "developer": "CREATIVE ASSEMBLY",
  "publisher": "SEGA",
  "price": "$11.99",
  "type": "dlc",
  "base_game_name": "Total War: WARHAMMER III",
  "platforms": ["Windows", "macOS", "Linux"],
  "review_summary": "Mixed",
  "review_count": "482",
  "tags": ["Strategy", "Action", "Turn-Based Strategy"],
  "genres": ["Strategy"],
  "features": ["Single-player", "Multi-player"],
  "screenshot_count": 15,
  "has_trailer": true,
  "url": "https://store.steampowered.com/app/1670540/..."
}
```

### Search Results Response

```json
{
  "success": true,
  "query": "Total War Warhammer",
  "results": [
    {
      "appid": "1142710",
      "title": "Total War: WARHAMMER III",
      "url": "https://store.steampowered.com/app/1142710/...",
      "price": "$59.99",
      "release_date": "Feb 17, 2022"
    }
  ],
  "total": 10
}
```

## Notes

- The skill handles Steam's age verification gate automatically
- DLC pages include base game information when available
- Discounted prices include both original and final price
- Free-to-play games are marked with `is_free: true`
- System requirements are extracted per platform when available
