# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Metacritic TV Show Access Skill

This skill fetches TV show information from [Metacritic](https://www.metacritic.com), including metascores, critic reviews, and detailed cast/crew information.

## Features

### get_tv_show_info
Fetches basic TV show information including:
- Title, description, and image
- Metascore (critic aggregate score) with review count
- Genres, content rating, release date
- Creators, actors, and production companies
- Trailer information

**Example:**
```json
{
  "function": "get_tv_show_info",
  "show_slug": "adolescence"
}
```

**Returns:**
```json
{
  "url": "https://www.metacritic.com/tv/adolescence/",
  "title": "Adolescence",
  "description": "13-year-old Jamie Miller (Owen Cooper) is accused of murdering a classmate...",
  "metascore": 91,
  "metascore_details": {
    "score": 91,
    "review_count": 29,
    "reviews_url": "https://www.metacritic.com/tv/adolescence/critic-reviews/"
  },
  "genres": ["Crime", "Drama", "Thriller"],
  "creators": ["Stephen Graham", "Jack Thorne", "Philip Barantini"],
  "actors": ["Owen Cooper", "Stephen Graham", "Ashley Walters", ...],
  ...
}
```

### get_critic_reviews
Fetches individual critic reviews including:
- Overall metascore
- Each review's score, publication, author, and quote
- Review date

**Example:**
```json
{
  "function": "get_critic_reviews",
  "show_slug": "adolescence"
}
```

**Returns:**
```json
{
  "url": "https://www.metacritic.com/tv/adolescence/critic-reviews/",
  "show_slug": "adolescence",
  "overall_score": 91,
  "review_count": 10,
  "reviews": [
    {
      "date": "MAR 4, 2025",
      "score": 100,
      "publication": "The Telegraph",
      "author": "Anita Singh",
      "quote": "It is a drama so quietly devastating that I won't forget it for a very long time."
    },
    ...
  ]
}
```

### get_show_details
Fetches comprehensive TV show details including:
- All information from get_tv_show_info
- User score and rating count
- Full cast list with profile links
- Full crew list (creators, directors, writers)
- Production companies
- Awards information

**Example:**
```json
{
  "function": "get_show_details",
  "show_slug": "adolescence"
}
```

## How to Find a Show Slug

The `show_slug` is the identifier in the Metacritic URL:

| Show URL | show_slug |
|----------|-----------|
| https://www.metacritic.com/tv/adolescence/ | `adolescence` |
| https://www.metacritic.com/tv/the-last-of-us/ | `the-last-of-us` |
| https://www.metacritic.com/tv/shogun/ | `shogun` |
| https://www.metacritic.com/tv/house-of-the-dragon/ | `house-of-the-dragon` |

## Notes

- The skill uses Playwright browser automation to handle Metacritic's JavaScript-rendered pages
- Data is extracted from JSON-LD structured data embedded in pages for reliability
- Some pages may take a few seconds to fully render due to heavy JavaScript
- The details page may timeout in some cases; the skill falls back to the main page in such cases
- Scores are color-coded by Metacritic: Green (61-100), Yellow (40-60), Red (0-39)

## Error Handling

The skill returns structured error responses:
- `{"error": "show_slug parameter is required"}` - Missing required parameter
- `{"error": "Could not extract show data from page"}` - Page loaded but data not found
- `{"error": "Failed to fetch show info: ..."}` - Network or other error
