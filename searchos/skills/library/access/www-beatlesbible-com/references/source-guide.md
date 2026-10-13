# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Beatles Bible Access Skill

Fetches structured discography data from [Beatles Bible](https://www.beatlesbible.com), a comprehensive reference site for Beatles recordings, releases, and history.

## Important Note

**Cloudflare Protection**: This site uses Cloudflare Turnstile bot protection that may block automated access. The skill includes challenge handling, but if the site blocks requests, it will return an error message. Access may work intermittently depending on Cloudflare's detection.

## Features

### get_discography
Retrieves the complete UK discography listing from Beatles Bible. Returns a list of all UK releases with names, URLs, types, dates, and catalog numbers when available.

**Example:**
```json
{
  "function": "get_discography"
}
```

**Returns on success:**
```json
{
  "success": true,
  "data": {
    "page_title": "UK discography",
    "description": "A list of all Beatles releases in the United Kingdom...",
    "releases": [
      {
        "name": "Love Me Do",
        "url": "https://www.beatlesbible.com/1962/10/05/uk-single-love-me-do-ps-i-love-you/",
        "type": "Single",
        "date": "5 October 1962",
        "catalog_number": "Parlophone R 4949"
      }
    ]
  },
  "source": "beatlesbible.com",
  "url": "https://www.beatlesbible.com/discography/united-kingdom/"
}
```

**Returns on Cloudflare block:**
```json
{
  "success": false,
  "error": "Cloudflare challenge did not resolve within timeout. The site may be blocking automated access. Try again later or use a different IP.",
  "source": "beatlesbible.com",
  "url": "https://www.beatlesbible.com/discography/united-kingdom/"
}
```

### get_release
Retrieves detailed information about a specific Beatles release, including tracklist, release date, catalog number, chart positions, and description.

**Parameters:**
- `url` (required): The URL of the release page, either full URL or relative path

**Example:**
```json
{
  "function": "get_release",
  "url": "https://www.beatlesbible.com/1966/08/05/uk-single-eleanor-rigby-yellow-submarine/"
}
```

Or with relative path:
```json
{
  "function": "get_release",
  "url": "/1966/08/05/uk-single-eleanor-rigby-yellow-submarine/"
}
```

**Returns on success:**
```json
{
  "success": true,
  "data": {
    "url": "https://www.beatlesbible.com/1966/08/05/uk-single-eleanor-rigby-yellow-submarine/",
    "title": "Eleanor Rigby / Yellow Submarine",
    "type": "Single",
    "release_date": "5 August 1966",
    "catalog_number": "Parlophone R 5465",
    "tracks": [
      {"number": "A", "title": "Eleanor Rigby", "duration": "2:07"},
      {"number": "B", "title": "Yellow Submarine", "duration": "2:38"}
    ],
    "chart_positions": [],
    "description": "..."
  },
  "source": "beatlesbible.com"
}
```

### search_releases
Searches the discography for releases matching a query string. Since Beatles Bible doesn't have a search API, this fetches the discography page and filters results locally.

**Parameters:**
- `query` (required): Search term to match against release names

**Example:**
```json
{
  "function": "search_releases",
  "query": "Eleanor Rigby"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "query": "Eleanor Rigby",
    "results": [
      {
        "title": "Eleanor Rigby / Yellow Submarine",
        "url": "https://www.beatlesbible.com/1966/08/05/uk-single-eleanor-rigby-yellow-submarine/",
        "type": "release"
      }
    ]
  },
  "source": "beatlesbible.com"
}
```

## Data Extraction

The skill extracts:
- **Discography pages**: Release names, URLs, types (single/album), release dates, catalog numbers
- **Release pages**: Title, type, release date, catalog number, track listings with durations, chart positions, description
- **Search results**: Matching release titles, URLs, and types

## Technical Details

- Uses Playwright for browser automation with Cloudflare challenge handling
- Waits up to 15 seconds for Cloudflare Turnstile to resolve
- Includes stealth scripts to reduce bot detection
- Parses HTML using BeautifulSoup for structured data extraction

## Source

Data is fetched from: https://www.beatlesbible.com

The site's robots.txt permits search indexing (`Content-Signal: search=yes`).
