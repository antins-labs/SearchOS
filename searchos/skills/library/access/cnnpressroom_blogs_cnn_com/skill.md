# CNN Pressroom Blog Access Skill

This skill provides programmatic access to CNN's press release blog at `cnnpressroom.blogs.cnn.com` via the WordPress REST API.

## Overview

CNN Pressroom is CNN's official blog for press releases, announcements, and media alerts. The site covers:
- Programming announcements
- Personnel news (hires, promotions)
- Awards and recognition
- Special events and coverage
- CNN Heroes announcements
- Documentary and film premieres

## Functions

### get_post
Retrieve a single press release by its ID or URL slug.

**Parameters:**
- `post_id` (integer): The numeric post ID
- `slug` (string): The URL slug from the post URL
- `include_content` (boolean): Include full article content (default: true)
- `embed` (boolean): Include embedded data like author and categories (default: true)

**Example:**
```python
# By ID
result = await execute({
    'function': 'get_post',
    'post_id': 51401
})

# By slug (from URL)
result = await execute({
    'function': 'get_post',
    'slug': 'stephen-knight-named-2024-cnn-hero-of-the-year'
})
```

**Returns:** A `post` object with title, content, excerpt, date, author, categories, tags, and featured image.

### list_posts
List press releases with optional filters.

**Parameters:**
- `per_page` (integer): Results per page (default: 10, max: 100)
- `page` (integer): Page number for pagination
- `category_id` (integer): Filter by category ID
- `category_slug` (string): Filter by category slug
- `author_id` (integer): Filter by author ID
- `search` (string): Search within posts
- `after` (string): ISO date string for posts after this date
- `before` (string): ISO date string for posts before this date
- `include_content` (boolean): Include full content (default: false)

**Example:**
```python
# Recent posts
result = await execute({
    'function': 'list_posts',
    'per_page': 20
})

# Posts from a specific category
result = await execute({
    'function': 'list_posts',
    'category_slug': 'cnn-heroes',
    'per_page': 10
})

# Posts in date range
result = await execute({
    'function': 'list_posts',
    'after': '2024-01-01T00:00:00',
    'before': '2024-12-31T23:59:59'
})
```

**Returns:** Object with `posts` array, `total` count, `total_pages`, and pagination info.

### search_posts
Search press releases by keyword.

**Parameters:**
- `query` (string, required): Search query
- `per_page` (integer): Results per page (default: 10)
- `page` (integer): Page number
- `include_content` (boolean): Include full content (default: false)

**Example:**
```python
result = await execute({
    'function': 'search_posts',
    'query': 'CNN Hero of the Year'
})
```

### list_categories
Get all available categories.

**Parameters:**
- `per_page` (integer): Results per page (default: 50)
- `orderby` (string): Sort order, e.g., 'count' for most used categories

**Example:**
```python
result = await execute({
    'function': 'list_categories',
    'orderby': 'count',
    'per_page': 20
})
```

**Returns:** Object with `categories` array containing id, name, slug, and count.

### get_category
Get details of a single category.

**Parameters:**
- `category_id` (integer): Category ID
- `slug` (string): Category slug

**Example:**
```python
result = await execute({
    'function': 'get_category',
    'slug': 'cnn-heroes'
})
```

### extract_announcement
Extract structured announcement data from a press release. Optimized for CNN press release format.

**Parameters:**
- `post_id` (integer): Post ID
- `slug` (string): Post slug

**Example:**
```python
result = await execute({
    'function': 'extract_announcement',
    'post_id': 51401
})
```

**Returns:** An `announcement` object with:
- Basic post info (id, title, link, date, author, categories)
- `dateline_city`: City from press release dateline (e.g., "NEW YORK, NY")
- `dateline_date`: Date from dateline
- `summary`: First paragraph summary
- `key_quotes`: Extracted quotes from the release
- `content`: Full text content
- `content_html`: Original HTML content

## Response Structure

All functions return dictionaries with either a results key or an `error` key:

**Success:**
```json
{
  "post": { ... },
  ...
}
```

**Error:**
```json
{
  "error": "Post not found"
}
```

## Post Object Structure

```json
{
  "id": 51401,
  "title": "Stephen Knight Named 2024 CNN Hero of the Year",
  "slug": "stephen-knight-named-2024-cnn-hero-of-the-year",
  "link": "https://cnnpressroom.blogs.cnn.com/2024/12/08/...",
  "date": "2024-12-08T21:00:57",
  "date_gmt": "2024-12-08T21:00:57",
  "modified": "2024-12-08T20:11:15",
  "author": {
    "id": 196398287,
    "name": "sophietran",
    "slug": "sophietran",
    "link": "https://cnnpressroom.blogs.cnn.com/author/sophietran/"
  },
  "categories": [
    {"id": 3003861, "name": "CNN Heroes", "slug": "cnn-heroes"}
  ],
  "tags": [],
  "excerpt": "NEW YORK, NY – (December 8, 2024) – Tonight at the 18th Annual CNN Heroes...",
  "content_text": "NEW YORK, NY – (December 8, 2024) – Tonight at the 18th Annual...",
  "content_html": "<p><strong>NEW YORK, NY – (December 8, 2024</strong>)..."
}
```

## Common Categories

Some frequently used categories:
- `cnn-heroes` (ID: 3003861) - CNN Heroes announcements
- `ac360` (ID: 944267) - Anderson Cooper 360
- `awards` (ID: 6758) - Awards and recognition
- `amanpour` (ID: 1645317) - Christiane Amanpour

## Notes

- The site contains 7,000+ press releases dating back many years
- Posts are typically short press releases (1-3 paragraphs)
- Most posts follow a standard press release format with city/date dateline
- The API is publicly accessible without authentication
- Rate limiting may apply; consider reasonable delays between requests