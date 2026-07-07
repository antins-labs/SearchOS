# Sports Media Watch API

Access sports TV ratings and viewership data from [Sports Media Watch](https://www.sportsmediawatch.com).

## Overview

Sports Media Watch is a leading source for detailed TV ratings data for sports broadcasts, including NFL, NBA, MLB, college football, and more. This skill provides programmatic access to their comprehensive database of 17,000+ articles containing viewership numbers, ratings, and analysis.

**Note:** The site previously used blocking/rate limiting that required specific HTTP client configuration (httpx with `follow_redirects=False`). The WordPress REST API at `/wp-json/wp/v2/` is fully accessible with proper headers.

## Available Functions

### get_post_by_slug
Get a specific article by its URL slug with full content and extracted ratings data.

```python
params = {
    "function": "get_post_by_slug",
    "slug": "super-bowl-viewership-breakdown-record-audience-were-more-people-watching",
    "include_content": True  # Extract ratings data
}
```

Returns: Post with title, date, link, content, and extracted `ratings_data` object containing:
- `ratings`: List of household ratings (e.g., 41.7, 38.2)
- `viewership_millions`: List of viewership numbers in millions
- `percentages`: List of percentage changes
- `peaks`: List of peak viewership values

### get_post_by_id
Get a specific article by its WordPress post ID.

```python
params = {
    "function": "get_post_by_id",
    "post_id": 131208,
    "include_content": True
}
```

### search_posts
Search articles by keyword with pagination.

```python
params = {
    "function": "search_posts",
    "query": "super bowl ratings",
    "per_page": 20,
    "page": 1
}
```

Returns paginated results with total count.

### get_posts_by_category
Get articles from a specific category by name or ID.

```python
# By name
params = {
    "function": "get_posts_by_category",
    "category": "nfl",
    "per_page": 10
}

# By ID
params = {
    "function": "get_posts_by_category",
    "category_id": 11,
    "per_page": 10
}
```

**Category Mappings:**
| Name | ID | Posts |
|------|------|-------|
| ratings | 4 | 11,737+ |
| espn | 18 | 6,035+ |
| nfl | 11 | 3,744+ |
| nba | 3 | 3,605+ |
| nbc | 49 | 3,589+ |
| fox | 20 | 3,252+ |
| cbs | 53 | 2,664+ |
| mlb | 15 | 2,397+ |
| cfb | 17 | 2,368+ |
| tnt-sports | 5 | 2,252+ |

### get_posts_by_tag
Get articles with a specific tag.

```python
params = {
    "function": "get_posts_by_tag",
    "tag": "nfl-ratings",
    "per_page": 10
}
```

**Popular Tag Mappings:**
| Name | ID | Posts |
|------|------|-------|
| final-ratings | 136 | 5,093+ |
| overnights | 134 | 1,967+ |
| nba-ratings | 141 | 1,368+ |
| nfl-ratings | 148 | 1,148+ |
| cfb-ratings | 147 | 1,139+ |
| golf-ratings | 167 | 887+ |
| nba-on-espn | 119 | 1,179+ |
| nba-on-tnt | 118 | 1,104+ |

### list_categories
List all categories with post counts.

```python
params = {
    "function": "list_categories",
    "per_page": 20,
    "orderby": "count",
    "order": "desc"
}
```

### list_tags
List all tags with post counts.

```python
params = {
    "function": "list_tags",
    "per_page": 20,
    "orderby": "count",
    "order": "desc",
    "search": "ratings"  # Optional filter
}
```

### get_recent_posts
Get the most recent articles.

```python
params = {
    "function": "get_recent_posts",
    "per_page": 10
}
```

## Example Output

```python
{
    "posts": [
        {
            "id": 131208,
            "title": "Final Super Bowl viewership officially at record-high",
            "slug": "super-bowl-viewership-breakdown-record-audience-were-more-people-watching",
            "date": "2025-02-11T22:53:27",
            "link": "https://www.sportsmediawatch.com/...",
            "content": "The Super Bowl set another viewership record...",
            "ratings_data": {
                "ratings": [41.7, 43.5, 42.0, 40.7, 38.4],
                "viewership_millions": [127.7, 123.7, 137.7, 133.5],
                "percentages": [3, 4, 14, 5, 27],
                "peaks": [137.7]
            }
        }
    ]
}
```

## Use Cases

1. **Historical Research**: Track viewership trends for specific sports, teams, or events over time
2. **Data Analysis**: Extract structured ratings data for analysis and visualization
3. **Breaking News**: Get the latest ratings for recent playoff games, finals, major events
4. **Cross-sport Comparison**: Compare NBA Finals vs Stanley Cup vs World Series viewership
5. **Network Performance**: Analyze how different networks (ESPN, FOX, CBS, NBC) perform

## Notes

- All functions return structured dictionaries with explicit error fields for user/input errors
- Pagination supported via `page` and `per_page` parameters
- `include_content: true` fetches full article content and extracts ratings data
- Set `hide_empty: false` in list functions to see categories/tags with no posts
- Total results available via `total` field in paginated responses