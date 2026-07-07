# IDEAS/RePEc Access Skill

Access bibliographic data from IDEAS (Internet Documents in Economics Access Service), part of RePEc (Research Papers in Economics).

## Overview

IDEAS/RePEc is a comprehensive database of economic literature including:
- Journal articles from hundreds of economics journals
- Working papers from universities and research institutions
- Book chapters
- Software components
- Author profiles and rankings

## Functions

### get_article

Get detailed information about a specific article.

**Parameters:**
- `handle` (required): RePEc handle or article URL
  - Handle format: `archive:series:details` (e.g., `bla:ajecsc:v:85:y:2026:i:3:p:303-314`)
  - URL format: `https://ideas.repec.org/a/bla/ajecsc/v85y2026i3p303-314.html`

**Returns:**
```json
{
  "success": true,
  "article": {
    "url": "https://ideas.repec.org/a/bla/ajecsc/v85y2026i3p303-314.html",
    "handle": "RePEc:bla:ajecsc:v:85:y:2026:i:3:p:303-314",
    "title": "Article Title",
    "authors": ["Author Name"],
    "abstract": "Abstract text...",
    "journal": "Journal Name",
    "publisher": "Publisher",
    "year": "2024",
    "volume": "85",
    "issue": "3",
    "pages": "303-314",
    "doi": "10.xxxx/xxxxx",
    "keywords": [],
    "jel_codes": ["F21", "O11"],
    "has_download": true,
    "free_download": false,
    "suggested_citation": "Citation string..."
  }
}
```

**Example:**
```python
result = await execute({
    'function': 'get_article',
    'handle': 'bla:ajecsc:v:85:y:2026:i:3:p:303-314'
})
```

### get_serial

Get journal/serial information and list of recent articles.

**Parameters:**
- `handle` (required): RePEc serial handle or URL
  - Handle format: `archive:series` (e.g., `bla:ajecsc`)
  - URL format: `https://ideas.repec.org/s/bla/ajecsc.html`

**Returns:**
```json
{
  "success": true,
  "serial": {
    "url": "https://ideas.repec.org/s/bla/ajecsc.html",
    "title": "American Journal of Economics and Sociology",
    "publisher": "Wiley Blackwell",
    "handle": "bla:ajecsc",
    "issues": [
      {"date": "May 2026", "volume": "85", "issue": "3"}
    ],
    "articles": [
      {
        "url": "https://ideas.repec.org/a/bla/ajecsc/v85y2026i3p303-314.html",
        "title": "Article Title",
        "volume": "85",
        "year": "2026",
        "issue": "3",
        "pages": "303-314"
      }
    ]
  }
}
```

**Example:**
```python
result = await execute({
    'function': 'get_serial',
    'handle': 'bla:ajecsc'
})
```

### search

Search IDEAS for economic literature.

**Parameters:**
- `query` (required): Search query string
- `search_field` (optional): Field to search in
  - `all` (default): Search in all fields
  - `title`: Search in titles only
  - `author`: Search in author names
  - `abstract`: Search in abstracts
  - `keywords`: Search in keywords
- `doc_type` (optional): Document type filter
  - `all` (default): All document types
  - `articles`: Journal articles only
  - `papers`: Working papers only
  - `chapters`: Book chapters only
  - `books`: Books only
  - `software`: Software components only
- `page` (optional): Page number for pagination (default: 1)

**Returns:**
```json
{
  "success": true,
  "query": "foreign direct investment",
  "search_field": "all",
  "doc_type": "articles",
  "page": 1,
  "total": 33371,
  "count": 10,
  "results": [
    {
      "url": "https://ideas.repec.org/a/...",
      "handle": "archive:series:details",
      "title": "Article Title",
      "type": "article",
      "authors": ["Author Name"],
      "context": "Surrounding text from search results..."
    }
  ]
}
```

**Example:**
```python
# Basic search
result = await execute({
    'function': 'search',
    'query': 'inflation targeting'
})

# Search in titles only
result = await execute({
    'function': 'search',
    'query': 'monetary policy',
    'search_field': 'title'
})

# Search for working papers
result = await execute({
    'function': 'search',
    'query': 'climate change economics',
    'doc_type': 'papers'
})

# Paginated results
result = await execute({
    'function': 'search',
    'query': 'economic growth',
    'page': 2
})
```

### get_citations

Get citation and download statistics for an article.

**Parameters:**
- `handle` (required): RePEc handle of the article

**Returns:**
```json
{
  "success": true,
  "citations": {
    "handle": "RePEc:bla:ajecsc:v:85:y:2026:i:3:p:303-314",
    "downloads": "1523",
    "abstract_views": "3542",
    "citations": []
  }
}
```

**Example:**
```python
result = await execute({
    'function': 'get_citations',
    'handle': 'bla:ajecsc:v:85:y:2026:i:3:p:303-314'
})
```

## Handle Format

RePEc handles are unique identifiers for documents in the RePEc database. They follow the format:

```
archive:series:details
```

For example:
- Serial/Journal: `bla:ajecsc` (American Journal of Economics and Sociology)
- Article: `bla:ajecsc:v:85:y:2026:i:3:p:303-314`
- Working Paper: `nber:w12345`

URLs are automatically converted to handles, so you can use either format.

## Response Fields

### Article Fields
- `url`: IDEAS URL for the article
- `handle`: RePEc unique identifier
- `title`: Article title
- `authors`: List of author names
- `abstract`: Article abstract
- `journal`: Journal name
- `publisher`: Publisher name
- `year`: Publication year
- `volume`: Journal volume
- `issue`: Journal issue
- `pages`: Page range
- `doi`: DOI identifier (if available)
- `keywords`: Author keywords
- `jel_codes`: JEL classification codes
- `has_download`: Whether full text is available
- `free_download`: Whether download is free
- `suggested_citation`: Formatted citation string

### Search Result Fields
- `url`: IDEAS URL for the item
- `handle`: RePEc handle
- `title`: Item title
- `type`: Document type (article, paper, chapter, book, software)
- `authors`: List of authors (if detected)
- `context`: Surrounding text from search results

## Error Handling

All error responses include:
- `error`: Human-readable error message
- `error_code`: Machine-readable error code

Error codes:
- `INVALID_HANDLE`: The provided handle or URL could not be parsed
- `MISSING_PARAM`: Required parameter is missing
- `MISSING_FUNCTION`: No function specified
- `UNKNOWN_FUNCTION`: Unknown function name
- `FETCH_ERROR`: Failed to fetch the requested resource
- `SEARCH_ERROR`: Search request failed

## Rate Limiting

The skill respects rate limits with:
- 2 requests per second
- Maximum 5 concurrent requests

## Notes

1. **Free Access**: IDEAS/RePEc is a free service. Some linked full-text articles may require subscription access.

2. **Author Pages**: Author pages (`/e/` URLs) require author registration and are not directly accessible. Use search with `search_field: 'author'` to find author works.

3. **Citation Data**: The `get_citations` function queries LogEc for download and view statistics. Detailed citation lists may not be fully available.

4. **Search Tips**:
   - Use boolean operators: `+` for AND, `|` for OR, `~` for NOT
   - Phrase search: `"opportunity cost"`
   - Author/year search: `Smith (1776)` or `Kydland Prescott (1977)`
   - Synonyms are automatically expanded (labor=labour, USA=United States)
   - Word stemming is applied automatically

## Examples

### Find articles on a topic
```python
result = await execute({
    'function': 'search',
    'query': 'behavioral economics',
    'doc_type': 'articles'
})
for item in result['results'][:5]:
    print(f"{item['title']} - {', '.join(item['authors'])}")
```

### Get journal contents
```python
result = await execute({
    'function': 'get_serial',
    'handle': 'aea:aerrev'  # American Economic Review
})
print(f"Journal: {result['serial']['title']}")
for article in result['serial']['articles'][:10]:
    print(f"  {article['title']}")
```

### Look up an article
```python
result = await execute({
    'function': 'get_article',
    'handle': 'bla:ajecsc:v:85:y:2026:i:3:p:303-314'
})
article = result['article']
print(f"Title: {article['title']}")
print(f"Authors: {', '.join(article['authors'])}")
print(f"Journal: {article['journal']} ({article['year']})")
print(f"DOI: {article['doi']}")
```

### Search for author's work
```python
result = await execute({
    'function': 'search',
    'query': 'Joseph Stiglitz',
    'search_field': 'author'
})
print(f"Found {result['total']} works")
```