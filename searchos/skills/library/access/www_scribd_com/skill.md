# Scribd Document Access Skill

## Overview

This skill extracts document metadata and content from Scribd document pages. It attempts multiple access strategies to handle Scribd's anti-bot protection.

## Functions

### get_document

Fetches document metadata and content from a Scribd URL or document ID.

**Parameters:**
- `url` (string): Full Scribd document URL (e.g., `https://www.scribd.com/document/12345/document-title`)
- `doc_id` (string, optional): Scribd document ID - extracted from URL if not provided

**Returns:**
```json
{
  "success": true/false,
  "doc_id": "880794922",
  "url": "https://www.scribd.com/document/...",
  "document": {
    "title": "Document title",
    "description": "Document description",
    "author": "Author name",
    "page_count": 50,
    "pages": [...],
    "tables": [...]
  },
  "method": "browser" or "http",
  "access_attempts": [...]
}
```

**Example:**
```python
result = await execute({
    "function": "get_document",
    "url": "https://www.scribd.com/document/880794922/2025-QS-World-University-Rankings"
})
```

### extract_tables

Processes extracted table data into structured ranking information. Useful for processing data that has already been extracted from a document.

**Parameters:**
- `table_data` (array): Array of table row objects, each representing a row with consistent column keys

**Returns:**
```json
{
  "success": true/false,
  "total_rows": 100,
  "columns": ["rank", "institution", "country", "score"],
  "rankings": [
    {
      "rank": 1,
      "institution": "MIT",
      "country": "USA",
      "score": 100.0
    },
    ...
  ]
}
```

**Example:**
```python
result = await execute({
    "function": "extract_tables",
    "table_data": [
        {"Rank": "1", "University": "MIT", "Country": "USA"},
        {"Rank": "2", "University": "Stanford", "Country": "USA"}
    ]
})
```

## Access Strategies

The skill attempts multiple strategies to access Scribd documents:

1. **Browser Automation** (Playwright): Uses headless Chrome with JavaScript rendering and anti-detection measures
2. **HTTP Requests** (aiohttp): Direct HTTP requests with various user agents and header configurations

## Known Limitations

- **403 Forbidden**: Scribd aggressively blocks automated access. You may encounter consistent 403 responses due to:
  - IP-based blocking
  - User-agent detection
  - Regional restrictions
  - Document requiring authentication

## Workarounds for 403 Errors

If you encounter persistent 403 errors:

1. **Use a VPN**: Try accessing from a different IP address
2. **Wait and Retry**: Rate limiting may be temporary
3. **Browser Export**: Open the document manually in a browser and use the "Export" or "Download" feature
4. **Scribd Premium**: Some documents require a paid subscription

## Dependencies

- `playwright` (recommended): For browser automation access
- `aiohttp`: For direct HTTP access

Install with:
```bash
pip install aiohttp
pip install playwright && playwright install chromium
```

## Example Usage

```python
# Get document information
result = await execute({
    "function": "get_document",
    "url": "https://www.scribd.com/document/880794922/2025-QS-World-University-Rankings"
})

if result["success"]:
    document = result["document"]
    print(f"Title: {document.get('title')}")
    print(f"Pages: {document.get('page_count')}")
    
    if document.get('tables'):
        # Process ranking tables
        table_result = await execute({
            "function": "extract_tables",
            "table_data": document['tables'][0]
        })
        print(f"Found {table_result['total_rows']} rankings")
else:
    print(f"Access failed: {result.get('message')}")
```

## Supported Document Types

- PDF documents
- Presentations
- Spreadsheets
- Text documents
- Academic papers
- Reports

## Debug Information

When access fails, the result includes detailed debug information:

```json
{
  "success": false,
  "error": "access_blocked",
  "access_attempts": [
    {
      "method": "browser",
      "status_code": 403,
      "html_length": 39
    },
    {
      "method": "http",
      "attempts": [
        {"url": "...", "status": 403}
      ]
    }
  ]
}
```

## Notes

- Document IDs can be extracted from URLs automatically
- The skill uses multiple stealth techniques to avoid detection
- Results may vary based on network location and timing
- Large documents may take longer to process