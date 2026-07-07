# Lana Del Rey Fandom Wiki

This skill provides access to the Lana Del Rey Fandom Wiki through the MediaWiki API, allowing structured retrieval of wiki content including album information, artist details, track listings, and more.

## Features

### 1. Get Page Information (`get_page`)

Retrieve comprehensive page information including:
- Page title and URL
- Table of contents (sections list)
- Infobox data (when present)
- Disambiguation links (for disambiguation pages)
- Optional intro text

**Parameters:**
- `page` (required): Page name, e.g., "Lana_Del_Rey", "Ultraviolence_(album)"
- `include_content` (optional): Include cleaned intro text

**Example:**
```python
result = await execute({
    "function": "get_page",
    "page": "Ultraviolence_(album)",
    "include_content": True
})
```

### 2. Get Infobox Data (`get_infobox`)

Extract structured infobox data from album or artist pages. Albums typically include:
- Cover image
- Release date
- Recording dates
- Length
- Labels
- Producers

Artist pages include:
- Profile image
- Full name
- Birth date
- Hometown
- Occupation
- Website

**Parameters:**
- `page` (required): Page name

**Example:**
```python
result = await execute({
    "function": "get_infobox",
    "page": "Lana_Del_Rey"
})
```

### 3. Get Track Listing (`get_tracklist`)

Extract track listings from album pages with automatic section detection.

**Parameters:**
- `page` (required): Album page name
- `section` (optional): Section index (auto-detected if not provided)

**Returns:**
- Tracklists grouped by edition (Standard, Deluxe, etc.)
- Each track includes: number, title, writers, producers, length
- Total track count

**Example:**
```python
result = await execute({
    "function": "get_tracklist",
    "page": "Born_to_Die_(album)"
})
```

### 4. Search (`search`)

Search the wiki for pages.

**Parameters:**
- `query` (required): Search query
- `limit` (optional): Max results (default 10, max 50)

**Example:**
```python
result = await execute({
    "function": "search",
    "query": "ultraviolence song",
    "limit": 5
})
```

### 5. Get Category Pages (`get_category_pages`)

List all pages in a wiki category.

**Parameters:**
- `category` (required): Category name (with or without "Category:" prefix)
- `limit` (optional): Max results (default 20, max 50)

**Common categories:**
- Albums
- Songs
- Music videos
- Tours
- Collaborations

**Example:**
```python
result = await execute({
    "function": "get_category_pages",
    "category": "Albums"
})
```

### 6. Get Section Content (`get_section`)

Retrieve content of a specific section by name or index.

**Parameters:**
- `page` (required): Page name
- `section` (required): Section index or name (e.g., "Track Listing", "Background")

**Example:**
```python
result = await execute({
    "function": "get_section",
    "page": "Lana_Del_Rey",
    "section": "Discography"
})
```

## Page Naming Conventions

- Main artist: `Lana_Del_Rey`
- Albums: `Album_Name_(album)` - e.g., `Born_to_Die_(album)`
- Songs: `Song_Name_(song)` - e.g., `Video_Games_(song)`
- Note: Some pages may be disambiguation pages with links to specific entries

## Response Format

All functions return structured dictionaries:
- Successful responses contain the requested data
- Error responses include:
  - `error`: Human-readable error message
  - `code`: Error code for programmatic handling

Common error codes:
- `missing_param`: Required parameter not provided
- `not_found`: Page or section not found
- `no_infobox`: Page exists but has no infobox
- `no_tracklist`: Album page has no track listing section
- `http_error`: HTTP request failed
- `timeout`: Request timed out

## Examples

### Get all albums
```python
# First search or get category
albums = await execute({
    "function": "get_category_pages",
    "category": "Albums",
    "limit": 20
})

# Then get details for each album
for album in albums['pages']:
    info = await execute({
        "function": "get_infobox",
        "page": album['title']
    })
```

### Complete album information
```python
# Get page with infobox and tracklist
page = await execute({
    "function": "get_page",
    "page": "Ultraviolence_(album)",
    "include_content": True
})

tracks = await execute({
    "function": "get_tracklist",
    "page": "Ultraviolence_(album)"
})
```