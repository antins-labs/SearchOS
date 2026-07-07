# Olympics.com Athlete Profiles Skill

Extract detailed athlete profiles, medals, and competition results from Olympics.com.

## Overview

This skill provides programmatic access to Olympic athlete data from the official Olympics.com website. It extracts structured data from athlete profile pages, including:

- **Athlete Information**: Name, biography, birth date/place, height, weight
- **Country Affiliation**: Country code and name
- **Sports & Disciplines**: Sports the athlete competes in
- **Olympic Participation**: First Olympics, total games count
- **Medal Records**: Gold, silver, bronze counts and detailed medal history
- **Competition Results**: Detailed results from Olympic competitions
- **Profile Images**: URLs to athlete photos

## Functions

### `get_athlete_profile`

Fetches comprehensive profile data for a specific Olympic athlete.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `athlete_slug` | string | Yes | The athlete's URL slug (e.g., 'usain-bolt', 'long-ma') |
| `language` | string | No | Language code (default: 'en'). Supported: 'en', 'zh', 'fr', 'es', etc. |

**Example Request:**
```json
{
  "function": "get_athlete_profile",
  "athlete_slug": "usain-bolt",
  "language": "en"
}
```

**Example Response:**
```json
{
  "success": true,
  "data": {
    "athlete": {
      "slug": "usain-bolt",
      "name": "Usain Bolt",
      "language": "en",
      "country": {
        "code": "JAM",
        "name": "Jamaica"
      },
      "birth_date": "1986-08-21",
      "birth_place": "Sherwood Content",
      "height": "195",
      "weight": "94",
      "sports": ["Athletics"],
      "disciplines": ["100m", "200m", "4x100m Relay"],
      "first_games": "Athens 2004",
      "games_count": 4,
      "medals": {
        "gold": 8,
        "silver": 0,
        "bronze": 0,
        "total": 8
      },
      "medal_details": [
        {"games": "Beijing 2008", "event": "100m", "medal": "gold"},
        {"games": "Beijing 2008", "event": "200m", "medal": "gold"},
        {"games": "Rio 2016", "event": "100m", "medal": "gold"}
      ],
      "results": [
        {"games": "Rio 2016", "event": "100m", "result": "Gold", "score": "9.81"}
      ],
      "biography": "Usain St. Leo Bolt is a Jamaican retired sprinter...",
      "profile_image": "https://...",
      "source_url": "https://www.olympics.com/en/athletes/usain-bolt"
    }
  },
  "url": "https://www.olympics.com/en/athletes/usain-bolt"
}
```

---

### `search_athletes`

Searches for athletes by name across the Olympics database.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | string | Yes | Search query (athlete name) |
| `language` | string | No | Language code (default: 'en') |
| `limit` | integer | No | Maximum results to return (default: 10) |

**Example Request:**
```json
{
  "function": "search_athletes",
  "query": "bolt",
  "limit": 5
}
```

---

### `list_athletes_by_country`

Retrieves a list of Olympic athletes from a specific country.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `country_code` | string | Yes | Three-letter country code (e.g., 'JAM', 'USA', 'CHN') |
| `language` | string | No | Language code (default: 'en') |
| `limit` | integer | No | Maximum athletes to return (default: 20) |

**Example Request:**
```json
{
  "function": "list_athletes_by_country",
  "country_code": "JAM",
  "limit": 10
}
```

---

## Data Source

This skill extracts data from the Olympics.com Next.js-powered website by:

1. Fetching the athlete profile page using Playwright (required for JavaScript rendering)
2. Parsing the embedded `__NEXT_DATA__` JSON payload
3. Structuring the data into a consistent format

### URL Patterns

- Athlete Profile: `https://www.olympics.com/{language}/athletes/{slug}`
- Athletes List: `https://www.olympics.com/{language}/athletes`
- Country Filter: `https://www.olympics.com/{language}/athletes?country={code}`

### Finding Athlete Slugs

Athlete slugs typically follow the format: `firstname-lastname`

Examples:
- Usain Bolt → `usain-bolt`
- Michael Phelps → `michael-phelps`
- Simone Biles → `simone-biles`
- Ma Long (Chinese) → `long-ma`

For non-Latin names, use the romanized version or check the URL on Olympics.com.

---

## Error Handling

The skill returns structured errors:

```json
{
  "success": false,
  "error": "Description of the error",
  "error_type": "TimeoutError",
  "athlete_slug": "example-athlete"
}
```

Common error types:
- `TimeoutError`: Site took too long to respond (may be blocking requests)
- `NetworkError`: Connection failed
- `ParseError`: Data found but couldn't be parsed

---

## Limitations

1. **Site Accessibility**: Olympics.com may occasionally block automated requests or have slow response times. The skill includes timeout handling and retry logic.

2. **Rate Limiting**: Respect rate limits - the Olympics.com servers may throttle excessive requests. Recommended: 0.5 requests/second, max 20/minute.

3. **Data Availability**: Some historical athletes may have limited data. Newly announced athletes may not yet have profiles.

4. **browser Dependency**: This skill requires Playwright with Chromium browser for rendering JavaScript.

---

## Caching

Athlete data changes infrequently (typically only after competitions). Results are cached for 24 hours by default.

---

## Use Cases

- **Historical Research**: Query medal counts and competition results
- **Athlete Comparisons**: Compare statistics across athletes
- **Country Analysis**: List athletes from specific countries
- **Content Generation**: Populate athlete databases or applications
- **Multi-language Support**: Access profiles in different languages

---

## Technical Notes

- Uses Playwright for browser automation
- Extracts data from `__NEXT_DATA__` JSON for reliability
- Falls back to HTML parsing when Next.js data unavailable
- Handles both English and internationalized athlete slugs
- Respects robots.txt and includes appropriate rate limiting