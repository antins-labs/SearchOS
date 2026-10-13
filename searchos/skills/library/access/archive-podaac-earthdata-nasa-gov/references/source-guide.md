# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# NASA PO.DAAC Archive Access Skill

Access scientific documentation and data files from NASA's Physical Oceanography 
Distributed Active Archive Center (PO.DAAC) archive.

## Overview

This skill provides access to the NASA PO.DAAC archive at `archive.podaac.earthdata.nasa.gov`, 
which hosts scientific documentation (primarily PDFs) and data files (text-based tables) 
related to physical oceanography, sea surface height, and climate data.

## Functions

### fetch_pdf

Fetch and parse a PDF document from the archive.

**Parameters:**
- `url` (required): Full URL to the PDF file
- `extract_text` (optional): Whether to extract text content (default: true)
- `max_text_pages` (optional): Maximum pages to process for text extraction (default: 50)

**Returns:**
- `status`: HTTP status code
- `pdf_info`: PDF metadata including:
  - `file_size_bytes`: File size
  - `pdf_version`: PDF format version
  - `has_linearized`: Whether optimized for web viewing
  - `is_encrypted`: Whether the PDF is encrypted
  - `page_count`: Number of pages (if detectable)
  - `metadata`: Document metadata (Title, Author, etc. if available)
  - `object_count`: Number of PDF objects
- `text_content`: Extracted text (if extract_text is true)

**Example:**
```json
{
  "function": "fetch_pdf",
  "url": "https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-docs/web-misc/nasa-ssh/NASA-SSH_V1_UserGuide.pdf"
}
```

### fetch_text_data

Fetch and parse a structured text data file from the archive.

**Parameters:**
- `url` (required): Full URL to the text data file
- `max_rows` (optional): Maximum number of data rows to return (default: 10000)

**Returns:**
- `status`: HTTP status code
- `metadata`: Header comments and metadata from the file
- `headers`: Column headers (detected or generated)
- `data`: Array of data rows
- `row_count`: Total number of data rows in file

**Example:**
```json
{
  "function": "fetch_text_data",
  "url": "https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-docs/nasa-ssh/NASA_SSH_GMSL_INDICATOR.txt"
}
```

### check_url

Check if a URL is accessible without downloading the full content.

**Parameters:**
- `url` (required): Full URL to check

**Returns:**
- `status`: HTTP status code
- `content_type`: Content-Type header
- `content_length`: Content-Length header
- `accessible`: Boolean indicating if URL is accessible

**Example:**
```json
{
  "function": "check_url",
  "url": "https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-docs/web-misc/nasa-ssh/NASA-SSH_V1_UserGuide.pdf"
}
```

### fetch_file

Generic file fetch that auto-detects file type and extracts appropriate information.

**Parameters:**
- `url` (required): Full URL to the file
- `max_rows` (optional): Maximum data rows for text files (default: 10000)

**Returns:**
- `status`: HTTP status code
- `file_type`: Detected file type (pdf, text, or binary)
- Type-specific extracted information

**Example:**
```json
{
  "function": "fetch_file",
  "url": "https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-docs/web-misc/nasa-ssh/NASA-SSH_V1_UserGuide.pdf"
}
```

## Supported File Types

### PDF Documents
- Extracts document metadata (title, author, creation date, etc.)
- Extracts text content using FlateDecode decompression
- Supports linearized (web-optimized) PDFs
- Handles UTF-16 BE and UTF-8 text encoding

### Text Data Files
- Parses header comments (lines starting with # or ;)
- Auto-detects column delimiters (tab, comma, semicolon, whitespace)
- Extracts column headers
- Parses data rows into structured arrays
- Supports common scientific data file formats

## Notes

- The archive hosts NASA physical oceanography data and documentation
- Some URLs may return 404 if files have been moved or renamed
- PDF text extraction uses decompression of FlateDecode streams
- Text extraction quality depends on PDF structure and encoding
- Large files may take longer to process

## Common URL Patterns

- Documentation: `https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-docs/web-misc/<collection>/<filename>.pdf`
- Data files: `https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-docs/<collection>/<filename>.txt`

## Error Handling

All functions return an `error` field if something goes wrong:
- HTTP errors: `{"error": "HTTP 404"}`
- Timeouts: `{"error": "Request timed out"}`
- Missing parameters: `{"error": "Missing required parameter: url"}`
- Unknown function: `{"error": "Unknown function: <function_name>"}`
