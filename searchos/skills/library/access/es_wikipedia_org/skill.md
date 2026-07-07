# Spanish Wikipedia Infobox Extractor

Access skill for [Spanish Wikipedia](https://es.wikipedia.org) that extracts structured infobox data and article content.

## Features

- **Structured Infobox Extraction**: Reliably parses Wikipedia infobox tables into structured data with labeled fields
- **Article Content**: Retrieves introduction text and article summary
- **Search**: Find articles by keyword
- **Redirect Handling**: Automatically follows page redirects (e.g., "Pablo_Fajardo" → "Pablo_Fajardo_Mendoza")

## Functions

### get_article

Retrieve a Wikipedia article with structured infobox data.

**Parameters:**
- `title` (required): Article title - can use spaces or underscores
- `include_content` (optional, default: true): Whether to include article introduction text

**Returns:**
```json
{
  "title": "Ricardo Pun Chong",
  "display_title": "Ricardo Pun Chong",
  "url": "https://es.wikipedia.org/wiki/Ricardo_Pun_Chong",
  "description": "médico peruano",
  "extract": "Ricardo Enrique Pun Chong médico peruano...",
  "infobox": {
    "found": true,
    "infobox_type": "biography",
    "name": "Ricardo Pun",
    "sections": ["Ricardo Pun", "Información personal", "Educación", "Información profesional"],
    "fields": {
      "Nombre de nacimiento": {
        "value": "Ricardo Enrique Pun Chong",
        "section": "Información personal"
      },
      "Nacimiento": {
        "value": "3 de agosto de 1971 Lima, Perú",
        "section": "Información personal"
      },
      "Ocupación": {
        "value": "Médico Cirujano, Conferencista, Coach Ontologico Certificado, Filántropo",
        "section": "Información profesional"
      }
    }
  },
  "content": {
    "paragraphs": ["..."],
    "text": "..."
  }
}
```

### search

Search for Wikipedia articles matching a query.

**Parameters:**
- `query` (required): Search keywords
- `limit` (optional, default: 10): Maximum results

**Returns:**
```json
{
  "query": "fajardo abogado",
  "total": 15,
  "results": [
    {
      "title": "Pablo Fajardo Mendoza",
      "snippet": "...",
      "wordcount": 3500,
      "url": "https://es.wikipedia.org/wiki/Pablo_Fajardo_Mendoza"
    }
  ]
}
```

## Example Usage

```python
# Get article with infobox
result = await execute({
    "function": "get_article",
    "title": "Ricardo_Pun_Chong"
})

# Search for articles
result = await execute({
    "function": "search",
    "query": "CNN Heroes Perú",
    "limit": 5
})
```

## Technical Notes

- Uses MediaWiki Parse API to fetch article HTML
- Uses Wikipedia REST API for summary metadata
- Parses infobox tables using BeautifulSoup with robust field extraction
- Handles Spanish-language infobox structure (Información personal, Educación, etc.)
- Normalizes whitespace and removes wikidata edit markers
- Follows Wikipedia's User-Agent policy for API access