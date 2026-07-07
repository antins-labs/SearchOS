# Yum! Brands Annual Reports Access Skill

Access Yum! Brands annual reports hosted on Q4 CDN (s2.q4cdn.com).

## Overview

This skill provides structured access to Yum! Brands annual reports hosted on Q4 Inc's CDN platform at `s2.q4cdn.com`. The site serves as the official repository for Yum! Brands' investor relations materials, including annual reports, proxy statements, CEO letters, and financial highlights.

## URL Structure

- **Base Pattern**: `https://s2.q4cdn.com/890585342/files/doc_financials/{year}/ar/annual-report-{year}/`
- **Company ID**: `890585342`
- **Available Years**: 2020, 2021, 2022, 2023, 2024

## Available Documents

Each annual report landing page provides access to:

| Document Type | Filename Pattern | Description |
|--------------|------------------|-------------|
| Annual Report | `{year}-annual-report.pdf` | Complete annual report |
| CEO Letter | `{year}arDavidLetter.pdf` | Letter from CEO David Gibbs |
| Proxy Statement | `YUM{year}_Combined-Proxy-10K.pdf` | Combined proxy and 10-K filing |
| Financial Highlights | `{year}-financial highlights.pdf` | Key financial metrics summary |
| Safe Harbor | `2017-Safe-Harbor-Statement.pdf` | Forward-looking statements disclaimer |

## Data Available

### From HTML Landing Page
- Report title and meta description
- Download links for all PDF documents
- Board of Directors (names and ages)
- Senior Officers (names and ages)
- Brand website links (KFC, Pizza Hut, Taco Bell, Habit Burger, Yum.com)
- Content preview/CEO letter excerpt

### From PDF Downloads
- Annual Report: ~10MB complete report
- CEO Letter: ~200KB executive letter
- Financial Highlights: ~30KB summary document
- Proxy Statement: ~9MB combined filing

## Functions

### `get_annual_report_info`
Get comprehensive metadata about a specific year's annual report.

**Parameters:**
- `year` (string): Report year, default "2024"
- `include_downloads` (boolean): Include PDF download links, default true
- `include_people` (boolean): Include board/officers info, default true

**Returns:** Report metadata, downloads, board members, senior officers

### `list_available_years`
Check which years have available annual reports.

**Parameters:**
- `check_years` (array): Years to check, default ["2020", "2021", "2022", "2023", "2024"]

**Returns:** List of available years with URLs

### `get_pdf_url`
Get direct download URL for a specific PDF document.

**Parameters:**
- `year` (string): Report year, default "2024"
- `document_type` (string): Type of document - "annual_report", "ceo_letter", "proxy_statement", "financial_highlights", "safe_harbor"
- `custom_filename` (string): Custom filename (optional, overrides document_type)

**Returns:** Full download URL and accessibility status

### `search_report_content`
Search for text within an annual report's HTML landing page.

**Parameters:**
- `year` (string): Report year, default "2024"
- `query` (string): Search query (case-insensitive)
- `context_chars` (integer): Context characters around matches, default 150

**Returns:** Matching text snippets with context

### `get_brand_links`
Get links to brand websites mentioned in the annual report.

**Parameters:**
- `year` (string): Report year, default "2024"

**Returns:** Brand websites (KFC, Pizza Hut, Taco Bell, Habit Burger, Yum.com)

## Technical Notes

### No Authentication Required
All resources are publicly accessible without authentication or cookies.

### CDN Performance
Files are served from Q4's CDN with good performance and reliability:
- HTML pages: ~75KB
- PDFs: 30KB to 10MB depending on document

### Rate Limiting
No apparent rate limiting detected. Standard HTTP requests with appropriate timeouts are recommended.

### Content Structure
The HTML landing pages use Bootstrap CSS with:
- Navigation bars for document downloads
- Sections for Board of Directors and Senior Officers
- Responsive image galleries
- External links to brand websites

## Example Usage

```python
# Get 2024 annual report details
result = await execute({
    "function": "get_annual_report_info",
    "year": "2024"
})

# Get CEO letter PDF URL
result = await execute({
    "function": "get_pdf_url",
    "year": "2024",
    "document_type": "ceo_letter"
})

# Search for digital strategy mentions
result = await execute({
    "function": "search_report_content",
    "year": "2023",
    "query": "digital"
})

# List all available years
result = await execute({
    "function": "list_available_years"
})
```

## Use Cases

1. **Investor Research**: Download annual reports and proxy statements for investment analysis
2. **Executive Information**: Extract board members and officers for corporate research
3. **Content Search**: Search report landing pages for specific topics or mentions
4. **Brand Research**: Get links to Yum! Brands portfolio companies

## Data Quality

- Board members and officers include names and ages extracted from structured HTML
- All download links are verified and direct URLs are provided
- Content previews are extracted from the main page content
- Brand links are categorized by company (KFC, Pizza Hut, Taco Bell, etc.)