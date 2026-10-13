# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# K-pop Fandom Wiki Access Skill

This skill retrieves K-pop artist information from kpop.fandom.com using the MediaWiki API. It extracts structured data from artist infoboxes including biographical details, career information, and social media links.

## Features

- **get_artist**: Retrieve detailed information about a specific artist by page title
- **search**: Search for artists and pages by name
- **get_by_ids**: Batch retrieve multiple pages by their page IDs

## Usage Examples

### Get Artist Information

```json
{
  "function": "get_artist",
  "title": "Lee Hi"
}
```

Returns:
- Page ID and URL
- Artist name and image
- Infobox data (birth name, birth date, height, weight, blood type, etc.)
- Career information (occupation, genres, debut, years active, agency)
- Fandom name
- Categories
- Description

### Search for Artists

```json
{
  "function": "search",
  "query": "IU",
  "limit": 10
}
```

Returns a list of matching pages with page IDs, titles, and snippets.

### Get Multiple Pages by IDs

```json
{
  "function": "get_by_ids",
  "page_ids": [7691, 2603, 3024]
}
```

Returns detailed information for multiple pages in a single request.

## Data Extracted

The skill extracts the following infobox fields when available:

**Background:**
- Birth name (Korean and Romanized)
- Birth date and age
- Birth place
- Height
- Weight
- Blood type

**Career:**
- Occupation
- Genres
- Group debut
- Solo debut
- Years active
- Agency (with time periods)
- Associated acts

**Personal:**
- Partner/Spouse
- Children

**Fandom:**
- Fandom name

## Notes

- The skill uses the MediaWiki API directly, bypassing Cloudflare protection
- All HTML is stripped from returned values
- Category names are cleaned (prefix removed)
- Page titles should match the wiki URL format (underscores or spaces both work)

## Error Handling

The skill returns structured error messages:
- Missing required parameters
- Page not found
- HTTP errors
- JSON parsing failures
