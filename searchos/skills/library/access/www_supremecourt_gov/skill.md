# Supreme Court Opinions Access Skill

Access Supreme Court slip opinions, orders, and PDF documents from www.supremecourt.gov.

## Overview

This skill provides programmatic access to the Supreme Court's opinions database. It can:

- **Retrieve slip opinions** by term (year)
- **Get opinions relating to orders** 
- **Download PDF documents** for opinions
- **Search opinions** by case name or docket number

## Technical Details

### Site Structure

The Supreme Court website uses a structured table format for listing opinions:

```
https://www.supremecourt.gov/opinions/slipopinion/{term}
```

Where `{term}` is a two-digit year (e.g., "24" for 2024).

### Opinion Table Structure

Each opinion includes:
- **R-** (Report number): Sequential opinion number for the term
- **Date**: Decision date
- **Docket**: Docket number (e.g., "24-809")
- **Name**: Case name (e.g., "Goldey v. Fields")
- **J.**: Justice who wrote the opinion (initials)
- **PDF Link**: Link to the full opinion PDF

### Bot Protection

**Important:** The Supreme Court website uses Akamai bot protection that blocks direct HTTP requests. This skill uses Playwright browser automation to:

1. Establish a valid session with cookies
2. Navigate through the opinion listings
3. Handle PDF downloads through the browser

Direct HTTP requests to the site will result in 403 Forbidden errors.

### Available Terms

Opinions are available for multiple terms:
- Current term: 25 (2025)
- Recent terms: 24, 23, 22, 21, 20...
- The archive appears to go back to at least 2000

## Functions

### get_slip_opinions

Retrieve all slip opinions for a given term.

**Parameters:**
- `term` (string, optional): Two-digit term year. Default: "24"

**Example:**
```python
result = await execute({
    "function": "get_slip_opinions",
    "term": "24"
})
```

**Response:**
```json
{
  "success": true,
  "term": "24",
  "title": "Opinions of the Court - 2024",
  "total_opinions": 67,
  "opinions": [
    {
      "report_number": "67",
      "date": "6/30/25",
      "docket": "24-809",
      "case_name": "Goldey v. Fields",
      "justice": "PC",
      "pdf_url": "https://www.supremecourt.gov/opinions/24pdf/606us2r67_8nka.pdf",
      "pdf_filename": "606us2r67_8nka.pdf",
      "term": "24"
    }
  ]
}
```

### get_relating_to_orders

Retrieve opinions relating to orders for a given term.

**Parameters:**
- `term` (string, optional): Two-digit term year. Default: "24"

**Example:**
```python
result = await execute({
    "function": "get_relating_to_orders",
    "term": "24"
})
```

### download_pdf

Download a Supreme Court opinion PDF.

**Parameters:**
- `pdf_url` (string, required): Full URL or path to PDF

**Example:**
```python
result = await execute({
    "function": "download_pdf",
    "pdf_url": "https://www.supremecourt.gov/opinions/24pdf/606us2r67_8nka.pdf"
})

# Or using just the path
result = await execute({
    "function": "download_pdf",
    "pdf_url": "24pdf/606us2r67_8nka.pdf"
})
```

**Response:**
```json
{
  "success": true,
  "pdf_url": "https://www.supremecourt.gov/opinions/24pdf/606us2r67_8nka.pdf",
  "filename": "606us2r67_8nka.pdf",
  "content_type": "application/pdf",
  "size_bytes": 181292,
  "data": "JVBERi0xLjQKJ..."
}
```

The `data` field contains the base64-encoded PDF content.

### search_opinions

Search opinions by case name or docket number.

**Parameters:**
- `query` (string, required): Search query
- `term` (string, optional): Limit to specific term

**Example:**
```python
# Search across recent terms
result = await execute({
    "function": "search_opinions",
    "query": "Trump"
})

# Search within specific term
result = await execute({
    "function": "search_opinions",
    "query": "24-809",
    "term": "24"
})
```

**Response:**
```json
{
  "success": true,
  "query": "Trump",
  "terms_searched": ["25", "24", "23", "22", "21"],
  "total_matches": 5,
  "matches": [
    {
      "report_number": "66",
      "date": "6/27/25",
      "docket": "24A884",
      "case_name": "Trump v. CASA, Inc.",
      "justice": "AB",
      "pdf_url": "https://www.supremecourt.gov/opinions/24pdf/606us2r66_j426.pdf",
      "term": "24"
    }
  ]
}
```

## Justice Abbreviations

The `justice` field uses initials for the authoring justice:
- EK: Elena Kagan
- AB: Amy Coney Barrett
- BK: Brett Kavanaugh
- PC:...
- etc.

## Error Handling

All functions return structured error responses:

```json
{
  "success": false,
  "error": "Description of the error",
  "error_type": "ErrorClassName"
}
```

Common error scenarios:
- Missing required parameters
- Invalid PDF URL
- Network/timeout errors
- Page structure changes

## Performance Notes

- Browser automation adds overhead (~3-5 seconds per request)
- PDF downloads may add additional time depending on file size
- Search operations query multiple terms sequentially

## Limitations

- Direct HTTP access is blocked by Akamai
- The skill cannot access opinions via simple aiohttp/httpx
- PDF URLs require a valid session from the opinions page
- Very old terms may have different page structures