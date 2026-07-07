# Grokipedia Access Skill

This skill fetches and extracts structured content from [Grokipedia](https://grokipedia.com), a wiki/encyclopedia website.

## Features

- **Structured Content Extraction**: Extracts page content organized into sections, each with:
  - Title and heading level (h2-h6)
  - Paragraphs
  - Lists (ordered and unordered)
  - Tables with headers and rows

- **Metadata Extraction**: Captures page metadata including:
  - Description
  - Keywords
  - Open Graph metadata

- **Table Parsing**: Automatically extracts tabular data with headers:
  - Tour dates
  - Statistics
  - Filmographies
  - Discographies
  - And other structured data

## Usage

### Get a Page by Slug

```python
result = await execute({
    'function': 'get_page',
    'slug': 'i_am_gloria_world_tour'
})
```

### Get a Page by Full URL

```python
result = await execute({
    'function': 'get_page',
    'url': 'https://grokipedia.com/page/i_am_gloria_world_tour'
})
```

## Response Structure

```json
{
  "success": true,
  "url": "https://grokipedia.com/page/i_am_gloria_world_tour",
  "title": "I Am Gloria World Tour",
  "slug": "i_am_gloria_world_tour",
  "abstract": "The I Am Gloria World Tour is the fourth concert tour...",
  "sections": [
    {
      "level": "h2",
      "title": "Background",
      "paragraphs": ["During the COVID-19 pandemic..."],
      "lists": [],
      "tables": []
    },
    {
      "level": "h3",
      "title": "Set list",
      "paragraphs": [],
      "lists": [
        {
          "type": "ul",
          "items": ["\"Light Years Away\"", "Grey Wolf", ...]
        }
      ],
      "tables": []
    },
    {
      "level": "h3",
      "title": "Tour dates",
      "paragraphs": [],
      "lists": [],
      "tables": [
        {
          "headers": ["Date", "City", "Country", "Venue", "Attendance"],
          "rows": [
            ["December 9, 2023", "Guangzhou", "China", "Guangdong Olympic Stadium", "—"],
            ...
          ]
        }
      ]
    }
  ],
  "tables": [...],
  "lists": [...],
  "metadata": {
    "description": "...",
    "keywords": "..."
  },
  "categories": []
}
```

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Page not found",
  "url": "https://grokipedia.com/page/nonexistent",
  "status_code": 404
}
```

Common errors:
- `Page not found` (404)
- `Either url or slug parameter is required`
- `URL must be from grokipedia.com domain`
- `Request timed out`
- `No article/main element found` (malformed page)

## Technical Notes

- Uses direct HTTP requests to fetch pages (no browser automation)
- Parses HTML with BeautifulSoup
- Handles Grokipedia's specific structure where paragraphs are in `<span class="mb-4">` elements
- Extracts tables, lists, and preserves document structure
- All content is extracted in plain text format