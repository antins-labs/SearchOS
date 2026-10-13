# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Memory Alpha Access Skill

Access structured data from [Memory Alpha](https://memory-alpha.fandom.com), the Star Trek wiki, via the MediaWiki API.

## Features

- **Article Retrieval**: Get complete article data including infobox, categories, links, and full content
- **Search**: Find articles by keyword or phrase
- **Category Browsing**: List articles within a specific category with pagination
- **Random Articles**: Discover random Star Trek content

## Functions

### get_article

Fetch a specific article by its title.

```python
# Example: Get article about Spock
result = await execute({
    "function": "get_article",
    "title": "Spock"
}, ctx)

# Returns:
{
    "title": "Spock",
    "pageid": 202697,
    "url": "https://memory-alpha.fandom.com/wiki/Spock",
    "description": "Short description...",
    "infobox": {
        "title": "Spock",
        "image": {"url": "...", "alt": "Spock"},
        "species": {"label": "Species", "value": "Human/Vulcan"},
        "affiliation": {"label": "Affiliation", "value": "Starfleet"},
        ...
    },
    "categories": ["Characters", "Vulcans", ...],
    "sections": [...],
    "content_text": "Full article text...",
    "content_html": "Full HTML content..."
}
```

Parameters:
- `title` (required): Article title, e.g., "Spock", "USS Enterprise (NCC-1701-D)"
- `include_content` (optional, default true): Include full article content

### search

Search for articles matching a query.

```python
# Example: Search for "Klingon"
result = await execute({
    "function": "search",
    "query": "Klingon",
    "limit": 10
}, ctx)

# Returns:
{
    "query": "Klingon",
    "count": 10,
    "results": [
        {
            "title": "Klingon",
            "pageid": 12345,
            "url": "https://memory-alpha.fandom.com/wiki/Klingon",
            "snippet": "The **Klingon** Empire...",
            "wordcount": 5000,
            "size": 35000
        },
        ...
    ]
}
```

Parameters:
- `query` (required): Search terms
- `limit` (optional, default 10, max 50): Maximum results

### get_category

List articles in a category.

```python
# Example: Get performers category
result = await execute({
    "function": "get_category",
    "category": "Performers",
    "limit": 20
}, ctx)

# Returns:
{
    "category": "Category:Performers",
    "count": 20,
    "members": [
        {"title": "William Shatner", "pageid": 123, "url": "..."},
        ...
    ],
    "continue": "next_page_token"  # If more results available
}
```

Parameters:
- `category` (required): Category name (with or without "Category:" prefix)
- `limit` (optional, default 20, max 50): Maximum results
- `continue` (optional): Pagination token from previous request

### random

Get random articles.

```python
# Example: Get 5 random articles
result = await execute({
    "function": "random",
    "limit": 5
}, ctx)

# Returns:
{
    "count": 5,
    "articles": [
        {"title": "Random Article", "pageid": 456, "url": "..."},
        ...
    ]
}
```

Parameters:
- `limit` (optional, default 5, max 10): Number of random articles

## Infobox Data

The `infobox` field contains parsed sidebar data with structured key-value pairs. Common fields include:

- `title`: Article title
- `image`: Image URL and alt text
- `species`, `gender`, `born`, `died`: Biographical information
- `affiliation`, `rank`, `position`: Organizational data
- `status`, `portrayed_by`: Additional metadata

## Categories

Memory Alpha uses categories extensively. Some useful ones:

- `Performers` - Actors and voice actors
- `Characters` - Fictional characters
- `Starships` - Spacecraft
- `Episodes` - TV episodes
- `Films` - Movies
- `Species` - Alien species
- `Planets` - Locations

## Notes

- The skill uses the MediaWiki API directly, bypassing Cloudflare protection
- All text content is cleaned of HTML markup in `content_text`
- Links are resolved to their canonical titles via API redirects
- Rate limiting is handled gracefully by the API
