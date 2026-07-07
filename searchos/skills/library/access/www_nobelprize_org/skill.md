# Nobel Prize Bibliography Access Skill

Extract structured bibliographical and biographical data from Nobel Prize laureate pages on nobelprize.org.

## Overview

The Nobel Prize website contains detailed bibliographies for Literature laureates and bio-bibliographies for recent prize years. These pages present valuable scholarly data in HTML format that can be challenging to parse programmatically. This skill provides structured access to this data.

## Supported Page Types

### 1. Laureate Bibliography Pages
**URL Pattern:** `/prizes/literature/{year}/{laureate}/bibliography/`

Example: `https://www.nobelprize.org/prizes/literature/1928/undset/bibliography/`

These pages contain:
- Tables organized by section (e.g., "Works in Norwegian", "Translations into English", "Critical studies")
- Each row contains a bibliographic entry in the format: `Title. – Place : Publisher, Year`

### 2. Bio-bibliography Pages
**URL Pattern:** `/prizes/literature/{year}/bio-bibliography/`

Example: `https://www.nobelprize.org/prizes/literature/2018/bio-bibliography/`

These pages contain:
- Biography section with narrative text
- Bibliography organized by language/section (e.g., "Bibliography – a selection", "In English", "In French")

## Functions

### get_bibliography
Returns complete structured data from a Nobel Prize bibliography page.

```python
result = await execute({
    "function": "get_bibliography",
    "url": "https://www.nobelprize.org/prizes/literature/1928/undset/bibliography/"
})
```

**Returns:**
- `metadata`: Page title, prize year, prize category
- `biography`: Biography text (for bio-bibliography pages)
- `bibliography`: Structured bibliography organized by sections
- `related_links`: Links to related pages (facts, speech, nominations, etc.)
- `total_entries`: Count of bibliography entries

### get_summary
Returns a simplified list of entries (title, year, section only).

```python
result = await execute({
    "function": "get_summary",
    "url": "https://www.nobelprize.org/prizes/literature/1954/hemingway/bibliography/"
})
```

### search_entries
Search for entries matching a query string.

```python
result = await execute({
    "function": "search_entries",
    "url": "https://www.nobelprize.org/prizes/literature/1928/undset/bibliography/",
    "query": "Kristin Lavransdatter"
})
```

## Bibliography Entry Structure

Each entry is parsed into structured fields:

| Field | Description | Example |
|-------|-------------|---------|
| `title` | Work title | "Kransen" |
| `year` | Publication year | "1920" |
| `place` | Publication place | "Christiania" |
| `publisher` | Publisher name | "Aschehoug" |
| `series` | Series information | "Kristin Lavransdatter; 1" |
| `translator` | Translator name | "Tiina Nunnally" |
| `original_title` | Original work title | "Dom dzienny, dom nocny" |
| `raw` | Original unparsed text | Full entry text |

## Example Use Cases

### Extract all works by a laureate
```python
result = await execute({
    "function": "get_bibliography",
    "url": "https://www.nobelprize.org/prizes/literature/1928/undset/bibliography/"
})

for section in result['bibliography']['sections']:
    print(f"\n{section['name']}:")
    for entry in section['entries']:
        print(f"  - {entry.get('title')} ({entry.get('year', 'n.d.')})")
```

### Find translations into a specific language
```python
result = await execute({
    "function": "search_entries",
    "url": "https://www.nobelprize.org/prizes/literature/1928/undset/bibliography/",
    "query": "translated"
})

for match in result['matches']:
    if 'translator' in match:
        print(f"{match['title']} - translated by {match['translator']}")
```

### Generate a chronological list
```python
result = await execute({
    "function": "get_summary",
    "url": "https://www.nobelprize.org/prizes/literature/1954/hemingway/bibliography/"
})

# Sort by year
entries = [e for e in result['entries'] if e.get('year')]
entries.sort(key=lambda x: x['year'])

for entry in entries:
    print(f"{entry['year']}: {entry['title']}")
```

## Notes

- The skill uses direct HTTP requests with BeautifulSoup parsing (no browser automation required)
- Rate limiting is set to 2 requests/second to be respectful to the Nobel Prize server
- Results are cached for 1 hour by default
- Not all laureates have bibliography pages; primarily Literature laureates have comprehensive bibliographies
- Bio-bibliography pages are typically available for recent Literature prizes (2015+)