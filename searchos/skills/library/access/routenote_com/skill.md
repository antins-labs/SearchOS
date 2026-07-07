# RouteNote Blog Access Skill

Access blog posts from [RouteNote Blog](https://routenote.com/blog) via the WordPress REST API. This skill specializes in extracting structured top lists (music charts, podcast rankings, audiobook lists) from Spotify Wrapped and similar articles.

## Overview

RouteNote is a digital music distribution platform, and their blog features regular updates on music industry news, streaming platform trends, and popular music charts. The WordPress REST API provides clean, structured access to all blog content.

## Functions

### `get_post`

Fetch a single blog post by slug or ID.

**Parameters:**
- `slug` (string, optional): Post URL slug (e.g., '2024-spotify-wrapped-top-lists')
- `id` (integer, optional): WordPress post ID

**Returns:**
- `post.id`: Post ID
- `post.title`: Post title
- `post.slug`: URL slug
- `post.date`: Publication date (ISO format)
- `post.link`: Full URL to post
- `post.excerpt`: Clean text excerpt
- `post.content`: Clean text content
- `post.content_html`: Raw HTML content

**Example:**
```python
result = await execute({
    "function": "get_post",
    "slug": "2024-spotify-wrapped-top-lists"
})
```

### `list_posts`

List recent blog posts with pagination.

**Parameters:**
- `per_page` (integer, default 10, max 100): Number of posts to return
- `page` (integer, default 1): Page number for pagination

**Returns:**
- `posts`: Array of post summaries
- `count`: Number of posts returned
- `page`: Current page
- `per_page`: Posts per page

**Example:**
```python
result = await execute({
    "function": "list_posts",
    "per_page": 20,
    "page": 1
})
```

### `extract_lists`

Extract structured ordered lists from a blog post. Ideal for Spotify Wrapped top charts, music rankings, and similar list-based content.

**Parameters:**
- `slug` (string, optional): Post URL slug
- `id` (integer, optional): WordPress post ID

**Returns:**
- `post`: Basic post info (id, title, slug, link)
- `lists`: Array of extracted lists, each with:
  - `heading`: The heading preceding the list
  - `count`: Number of items
  - `items`: Array of items with `title` and optional `url`
- `list_count`: Total number of lists found
- `total_items`: Total items across all lists

**Example:**
```python
result = await execute({
    "function": "extract_lists",
    "slug": "2024-spotify-wrapped-top-lists"
})
# Returns top artists, songs, albums, podcasts, audiobooks
```

### `search_posts`

Search blog posts by keyword.

**Parameters:**
- `search` (string, required): Search term
- `per_page` (integer, default 10, max 100): Number of results

**Returns:**
- `search_term`: The search query
- `posts`: Array of matching post summaries
- `count`: Number of results

**Example:**
```python
result = await execute({
    "function": "search_posts",
    "search": "spotify wrapped",
    "per_page": 15
})
```

## Use Cases

### 1. Get Spotify Wrapped Annual Charts

Extract annual top charts for artists, songs, albums, podcasts, and audiobooks:

```python
result = await execute({
    "function": "extract_lists",
    "slug": "2024-spotify-wrapped-top-lists"
})

for chart in result["lists"]:
    print(f"\n{chart['heading']}")
    for i, item in enumerate(chart["items"], 1):
        print(f"  {i}. {item['title']}")
```

### 2. Find Articles About Specific Topics

Search for articles about music platforms or trends:

```python
result = await execute({
    "function": "search_posts",
    "search": "tiktok music"
})
```

### 3. Browse Recent Music Industry News

```python
result = await execute({
    "function": "list_posts",
    "per_page": 20
})
```

## Data Extracted from Top Lists

The `extract_lists` function is optimized for Spotify Wrapped articles and similar chart-based posts. It extracts:

- **Most-Streamed Artists**: Global top artists with Spotify links
- **Most-Streamed Songs**: Top tracks with artist info and Spotify links
- **Most-Streamed Albums**: Top albums with artist info and Spotify links
- **Most Viral Songs**: Viral tracks with Spotify links
- **Top Podcasts**: Most popular podcasts with Spotify links
- **Top Audiobooks**: Most listened audiobooks with Spotify links

Each list item includes:
- `title`: The item name/ranking text
- `url`: Spotify link (if available in the article)

## Error Handling

All functions return structured error responses:

```python
{
    "error": "Human-readable error message",
    "error_code": "ERROR_CODE"
}
```

Error codes:
- `INVALID_PARAMS`: Missing or invalid parameters
- `NOT_FOUND`: Post not found
- `NETWORK_ERROR`: Network/connection issues
- `UNKNOWN_FUNCTION`: Unknown function name
- `UNEXPECTED_ERROR`: Unexpected error occurred

## Dependencies

- `aiohttp`: Async HTTP client for API requests
- `beautifulsoup4`: HTML parsing for list extraction

## Rate Limits

- 5 requests per second
- 100 requests per minute

Caching is enabled with a 1-hour TTL for optimal performance.