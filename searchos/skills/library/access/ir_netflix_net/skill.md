# Netflix Investor Relations Access Skill

This skill provides access to Netflix's investor relations data from [ir.netflix.net](https://ir.netflix.net), including SEC filings and annual reports.

## Features

### SEC Filings
- Access all SEC filings including 10-K, 10-Q, 8-K, Form 4 and other regulatory documents
- Filter by year and form type
- Get document download links (PDF, XLS formats)
- View filing metadata including dates, descriptions, and insider information

### Annual Reports & Proxies
- Access annual meeting information
- View proxy statements
- Get webcast links for annual meetings

## Available Functions

### `get_sec_filings_years`
Returns list of years for which SEC filings are available.

**Example:**
```javascript
{
  "function": "get_sec_filings_years"
}
```

**Returns:**
```json
{
  "years": [2026, 2025, 2024, 2023, 2022, ...]
}
```

### `get_sec_filings`
Retrieves SEC filings with optional filters.

**Parameters:**
- `year` (optional): Filter by year. Use -1 for all years.
- `form_type` (optional): Filter by form type (e.g., "10-K", "8-K", "4")
- `page` (optional): Page number (0-indexed, default: 0)
- `page_size` (optional): Results per page (default: 100, use -1 for all)

**Examples:**

Get all 2024 filings:
```javascript
{
  "function": "get_sec_filings",
  "year": 2024
}
```

Get 10-K filings only:
```javascript
{
  "function": "get_sec_filings",
  "form_type": "10-K",
  "year": -1
}
```

**Returns:**
```json
{
  "filings": [
    {
      "filing_id": 18023195,
      "form_type": "10-K",
      "form_description": "Annual Report",
      "filing_date": "01/26/2024 00:00:00",
      "documents": [
        {
          "document_type": "CONVPDF",
          "url": "https://d18rn0p25nwr6d.cloudfront.net/CIK-0001065280/...",
          "document_id": 19543202
        }
      ],
      ...
    }
  ],
  "total_count": 286
}
```

### `get_event_years`
Returns years for which annual reports/events are available.

**Example:**
```javascript
{
  "function": "get_event_years"
}
```

### `get_annual_reports`
Retrieves annual meeting and proxy information.

**Parameters:**
- `year` (optional): Filter by year. Use -1 for all years.

**Example:**
```javascript
{
  "function": "get_annual_reports"
}
```

**Returns:**
```json
{
  "reports": [
    {
      "event_id": 1199,
      "title": "Annual Meeting of Stockholders of Netflix, Inc.",
      "start_date": "06/05/2025 15:00:00",
      "is_webcast": true,
      "webcast_link": "https://www.virtualshareholdermeeting.com/NFLX2025",
      "tags": ["webcast", "annual"],
      ...
    }
  ],
  "total_count": 7
}
```

### `search_filings`
Search SEC filings by text query with optional filters.

**Parameters:**
- `query` (optional): Text to search in description/person name
- `year` (optional): Filter by year
- `form_type` (optional): Filter by form type
- `limit` (optional): Max results (default: 50)

**Example:**
```javascript
{
  "function": "search_filings",
  "query": "insider",
  "year": 2024
}
```

## Common SEC Form Types

- **10-K**: Annual Report
- **10-Q**: Quarterly Report
- **8-K**: Current Report (material events)
- **4**: Statement of Changes in Beneficial Ownership (insider trading)
- **4/A**: Amendment to Form 4
- **DEF 14A**: Definitive Proxy Statement
- **SC 13G**: Statement of acquisition of beneficial ownership
- **144**: Notice of proposed sale of securities

## Notes

- The API may have rate limits; the skill includes retry logic
- Document URLs point to Netflix's CloudFront CDN for PDF and XLS downloads
- Filing dates are in MM/DD/YYYY format
- All 6000+ historical filings since 2000 are accessible