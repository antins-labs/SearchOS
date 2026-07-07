# Wikipedia German (de.wikipedia.org) Access Skill

Extract structured tabular data from German Wikipedia pages, including award nominations/winners, navigation tables, and general wikitable data.

## Overview

This skill provides reliable access to structured data tables on German Wikipedia (de.wikipedia.org). It uses Playwright for browser automation to bypass Wikipedia's anti-bot protection and BeautifulSoup for robust HTML parsing.

## Functions

### `search`

Fetch a Wikipedia page and return metadata.

**Parameters:**
- `url` (string, optional): Full Wikipedia URL
- `page_title` (string, optional): Wikipedia page title (will construct URL)

**Returns:**
```json
{
  "success": true,
  "url": "https://de.wikipedia.org/wiki/...",
  "title": "Page Title – Wikipedia",
  "table_count": 2,
  "content_length": 191048
}
```

### `extract_tables`

Extract all wikitable data from a Wikipedia page.

**Parameters:**
- `url` (string, required): Full Wikipedia URL

**Returns:**
```json
{
  "success": true,
  "url": "...",
  "title": "...",
  "total_tables": 2,
  "tables": [
    {
      "table_index": 0,
      "headers": ["Jahr", "Interpret", "Nationalität", "Werk", "Weitere nominierte Künstler"],
      "row_count": 21,
      "column_count": 5,
      "data": [
        {"row_index": 1, "cells": ["1991|20. Februar 1991", "Big Daddy Kane, Ice-T, ...", ...]}
      ]
    }
  ]
}
```

### `extract_awards`

Extract award nominations/winners data with specialized parsing.

**Parameters:**
- `url` (string, required): Full Wikipedia URL to the awards page

**Returns:**
```json
{
  "success": true,
  "url": "...",
  "title": "...",
  "headers": ["Jahr", "Interpret", "Nationalität", "Werk", "Weitere nominierte Künstler"],
  "total_entries": 21,
  "awards": [
    {
      "year": "1991",
      "year_full": "1991|20. Februar 1991",
      "artist": "Big Daddy Kane, Ice-T, Kool Moe Dee, ...",
      "nationality": "Vereinigte Staaten",
      "work": "Back on the Block",
      "other_nominees": ["Digital Underground – The Humpty Dance", ...],
      "raw_cells": [...]
    }
  ]
}
```

### `fetch_page`

Fetch page and return raw HTML content.

**Parameters:**
- `url` (string, required): Full Wikipedia URL

**Returns:**
```json
{
  "success": true,
  "url": "...",
  "title": "...",
  "html": "<div>...</div>",
  "content_length": 191048
}
```

## Usage Examples

### Extract Grammy Awards Data

```python
result = await execute({
    "function": "extract_awards",
    "url": "https://de.wikipedia.org/wiki/Grammy_Award_for_Best_Rap_Performance_by_a_Duo_or_Group"
})

for award in result["awards"]:
    print(f"{award['year']}: {award['artist']} - {award['work']}")
```

### Search by Page Title

```python
result = await execute({
    "function": "search",
    "page_title": "Grammy Awards"
})
```

### Extract All Tables

```python
result = await execute({
    "function": "extract_tables",
    "url": "https://de.wikipedia.org/wiki/Liste_der_Grammy-Gewinner"
})

for table in result["tables"]:
    print(f"Table {table['table_index']}: {table['row_count']} rows")
```

## Data Format Notes

### Awards Table Structure

German Wikipedia awards tables typically follow this structure:
- **Jahr**: Year (may include ceremony date)
- **Interpret**: Artist/performer name(s)
- **Nationalität**: Country/nationality
- **Werk**: Work/title
- **Weitere nominierte Künstler**: Other nominees

### Text Separators

Cells with multiple lines use pipe (`|`) characters as separators in the extracted text to preserve structure while allowing easy parsing:

```
"1991|20. Februar 1991"  # Year and date
"Big Daddy Kane|,|Ice-T|,|..."  # Multiple artists
```

## Implementation Notes

### Browser Automation

This skill uses Playwright with headless Chromium because:
1. Wikipedia blocks direct HTTP requests from scripts (returns 403)
2. User-Agent headers alone are not sufficient
3. Browser context provides proper request signatures

### Rate Limiting

Consider implementing rate limiting for bulk requests to avoid being blocked by Wikipedia's servers.

### Character Encoding

German Wikipedia uses UTF-8 encoding. The skill handles German characters (ä, ö, ü, ß) and special formatting correctly.

## Error Handling

All errors are returned in the response with explicit error types:

```json
{
  "success": false,
  "error": "Page load timeout",
  "error_type": "timeout"
}
```

Common error types:
- `timeout`: Page load exceeded timeout
- `no_table`: No wikitable found in content
- `index_error`: Table index out of range
- `missing_parameter`: Required parameter not provided
- `invalid_function`: Unknown function name