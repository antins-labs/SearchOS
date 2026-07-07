# Italian Wikipedia Access Skill

This skill provides structured access to Italian Wikipedia (it.wikipedia.org) content, enabling extraction of page metadata, infobox data, bibliographies, and sections.

## Features

### 1. Page Information (`get_page`)
Fetches comprehensive metadata for a Wikipedia page:
- Title and page ID
- Last modified timestamp
- Page URL
- Text summary (first 5 sentences)
- Categories
- Wikidata ID

Example:
```python
result = await execute({
    "function": "get_page",
    "title": "Grazia_Deledda"
}, ctx)
```

### 2. Sections List (`get_sections`)
Extracts the table of contents for a Wikipedia page, including:
- Section index
- Section title
- Anchor link
- Section level

Example:
```python
result = await execute({
    "function": "get_sections",
    "title": "Luigi_Pirandello"
}, ctx)
```

### 3. Bibliography Extraction (`get_bibliography`)
Parses the bibliography section of a Wikipedia page:
- Finds the bibliography section automatically
- Extracts individual entries
- Identifies author and related links
- Supports limiting the number of results

Example:
```python
result = await execute({
    "function": "get_bibliography",
    "title": "Grazia_Deledda",
    "limit": 20
}, ctx)
```

### 4. Infobox Data (`get_infobox`)
Extracts structured data from Wikipedia infoboxes via Wikidata:
- Person information: birth/death dates and places, occupation, gender
- Awards and honors
- Family relations
- Education
- Other properties

The function uses Wikidata to get structured, machine-readable data that corresponds to Wikipedia infobox content.

Example:
```python
result = await execute({
    "function": "get_infobox",
    "title": "Luigi_Pirandello"
}, ctx)
```

### 5. Raw Wikidata (`get_wikidata`)
Fetches complete Wikidata entity for a Wikipedia page:
- Labels in multiple languages
- Descriptions
- Aliases
- All claims and statements
- Site links

Example:
```python
result = await execute({
    "function": "get_wikidata",
    "title": "Grazia_Deledda"
}, ctx)

# Or by Wikidata ID directly
result = await execute({
    "function": "get_wikidata",
    "wikidata_id": "Q7728"
}, ctx)
```

### 6. Search (`search`)
Searches Wikipedia pages by keyword:
- Returns title, snippet, and metadata
- Configurable result limit
- Direct links to pages

Example:
```python
result = await execute({
    "function": "search",
    "query": "Nobel letteratura italiano",
    "limit": 10
}, ctx)
```

## Data Sources

This skill uses:
1. **MediaWiki API** - For Wikipedia page content, sections, and search
2. **Wikidata API** - For structured infobox data

## Notes

- Page titles should use underscores for spaces (e.g., "Grazia_Deledda")
- The skill respects Wikipedia's User-Agent policy
- Wikidata lookups may be slow for entities with many properties
- Not all Wikipedia pages have Wikidata entries
- Bibliography extraction depends on the section structure (looks for "Bibliografia")

## Error Handling

All functions return structured error responses:
```python
{
    "error": "Error description here"
}
```

Common errors:
- Missing required parameters
- Page not found
- Missing Wikidata item
- Network timeouts