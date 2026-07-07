# Taylor Swift Fandom Wiki Access Skill

This skill extracts structured content from the Taylor Swift Fandom wiki at `taylorswift.fandom.com`.

## Features

- **Comprehensive Page Extraction**: Retrieves infoboxes, tables, content, sections, categories, and links
- **Structured Data**: Parses Fandom portable infoboxes into clean key-value pairs
- **Table Extraction**: Extracts wikitables with all cell data preserved
- **Tour Dates**: Specialized function to extract tour date tables from concerts
- **Wayback Fallback**: Automatically uses Wayback Machine archives when direct access is blocked by Cloudflare

## Functions

### `get_page`

Get complete page data including infobox, content, tables, sections, and metadata.

**Parameters:**
- `page_title` (required): The wiki page title (e.g., "Reputation_Stadium_Tour")

**Returns:**
- `success`: Boolean indicating if the request succeeded
- `page_title`: The actual page title
- `url`: The page URL
- `infobox`: Structured infobox data as key-value pairs
- `content`: Main page content text
- `tables`: List of tables, each being a list of rows
- `categories`: List of page categories
- `sections`: Page sections with headings and content
- `links`: Internal and external links

### `get_infobox`

Get only the infobox data from a page.

**Parameters:**
- `page_title` (required): The wiki page title

**Returns:**
- `success`: Boolean
- `page_title`: The page title
- `infobox`: Structured infobox data

### `get_tables`

Get only the table data from a page.

**Parameters:**
- `page_title` (required): The wiki page title

**Returns:**
- `success`: Boolean
- `tables`: List of tables with all cell data

### `get_tour_dates`

Extract tour date information from a tour page.

**Parameters:**
- `page_title` (required): The tour page title (e.g., "Reputation_Stadium_Tour")

**Returns:**
- `success`: Boolean
- `tour_dates`: List of tour dates with date, city, country, venue fields

### `search`

Search for pages in the wiki.

**Parameters:**
- `query` (required): Search query string
- `limit` (optional): Maximum results (default: 10)

**Returns:**
- `success`: Boolean
- `results`: List of search results with title, url, snippet

## Examples

### Get a Tour Page

```python
result = await execute({
    "function": "get_page",
    "page_title": "Reputation_Stadium_Tour"
})
# Returns infobox with tour info, table with 53 tour dates, etc.
```

### Extract Tour Dates

```python
result = await execute({
    "function": "get_tour_dates",
    "page_title": "Reputation_Stadium_Tour"
})
# Returns structured tour dates: date, city, country, venue for each show
```

### Get Infobox Only

```python
result = await execute({
    "function": "get_infobox",
    "page_title": "Taylor_Swift"
})
# Returns just the infobox data: birthdate, genres, labels, etc.
```

## Technical Notes

- The skill uses Wayback Machine archives when direct access is blocked
- Infobox parsing handles Fandom's portable infobox format
- Table extraction preserves row/colspan data
- Content extraction removes navboxes and TOC for cleaner text
- All text is normalized for whitespace

## Data Sources

- Primary: `https://taylorswift.fandom.com/wiki/`
- Fallback: `https://web.archive.org/web/2024/` (when Cloudflare blocks direct access)