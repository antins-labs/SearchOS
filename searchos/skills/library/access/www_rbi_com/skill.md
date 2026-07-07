# RBI Annual Reports Access Skill

Access Restaurant Brands International's annual reports and financial documents through their investor relations API.

## Overview

Restaurant Brands International (QSR) provides investor documents including:
- **10-K Annual Reports** - SEC filings
- **Proxy Statements** - Annual meeting and governance information
- **Restaurant Count Data** - Global store counts by market (PDF and Excel)
- **Annual Reports to Shareholders**

## Functions

### `list_reports`

Get all annual reports with document details.

```python
result = await execute({
    "function": "list_reports"
})
```

**Parameters:**
- `year` (integer, optional): Filter by specific year
- `include_documents` (boolean, default: true): Include document details

**Returns:**
```json
{
  "success": true,
  "count": 11,
  "reports": [
    {
      "id": 2596,
      "title": "2025 Annual Report",
      "year": 2025,
      "date": "12/31/2025 00:00:00",
      "sub_type": "Annual Report",
      "documents": [
        {
          "id": 7409,
          "title": "Restaurant Count by Market (Excel)",
          "category": "restaurantCountExcel",
          "type": "XLSX",
          "size": "7.33 MB",
          "url": "https://s26.q4cdn.com/...",
          "thumbnail": ""
        },
        {
          "id": 7418,
          "title": "10-K",
          "category": "tenk",
          "type": "PDF",
          "size": "2.73 MB",
          "url": "https://s26.q4cdn.com/...",
          "thumbnail": "https://s26.q4cdn.com/..."
        }
      ]
    }
  ]
}
```

### `list_years`

Get available report years.

```python
result = await execute({
    "function": "list_years"
})
```

**Returns:**
```json
{
  "success": true,
  "count": 11,
  "years": [2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015]
}
```

### `filter_reports`

Filter reports by year, document type, category, or search term.

```python
result = await execute({
    "function": "filter_reports",
    "year": 2024,
    "document_type": "PDF"
})
```

**Parameters:**
- `year` (integer, optional): Filter by year
- `document_type` (string, optional): Filter by type ('PDF', 'XLSX')
- `document_category` (string, optional): Filter by category ('tenk', 'proxy', 'restaurantCountpdf', etc.)
- `search` (string, optional): Search in report/document titles

### `get_document_urls`

Get all download URLs, optionally filtered.

```python
result = await execute({
    "function": "get_document_urls",
    "year": 2024,
    "document_type": "PDF"
})
```

**Returns:**
```json
{
  "success": true,
  "count": 3,
  "documents": [
    {
      "report_year": 2024,
      "report_title": "2024 Annual Report",
      "title": "Restaurant Count by Market (PDF)",
      "type": "PDF",
      "size": "437 KB",
      "category": "restaurantCountpdf",
      "url": "https://s26.q4cdn.com/...",
      "thumbnail": "https://s26.q4cdn.com/..."
    }
  ]
}
```

## Document Categories

| Category | Description |
|----------|-------------|
| `tenk` | SEC Form 10-K annual filing |
| `proxy` | Proxy statement |
| `annualreport` | Annual report to shareholders |
| `restaurantCountExcel` | Restaurant count data (Excel) |
| `restaurantCountpdf` | Restaurant count data (PDF) |

## Technical Notes

### API Endpoint

The skill uses RBI's internal FinancialReport API:
- **Base URL**: `https://www.rbi.com/feed/FinancialReport.svc`
- **Endpoints**:
  - `GetFinancialReportList` - List reports with documents
  - `GetFinancialReportYearList` - List available years

### Implementation

The site uses Cloudflare protection, so direct HTTP requests are blocked. This skill uses Playwright browser automation to:
1. Establish a valid browser session
2. Navigate to the investor relations page
3. Execute API calls from within the browser context
4. Return structured JSON data

### Document Hosting

Documents are hosted on Q4 CDN (`s26.q4cdn.com`) and can be downloaded directly using the URLs provided in the API responses.

## Examples

### Get all 10-K filings

```python
result = await execute({
    "function": "filter_reports",
    "document_category": "tenk"
})

for report in result['reports']:
    for doc in report['documents']:
        print(f"{report['year']}: {doc['url']}")
```

### Get the latest annual report

```python
years = await execute({"function": "list_years"})
latest_year = years['years'][0]

reports = await execute({
    "function": "list_reports",
    "year": latest_year
})

print(f"Latest report: {reports['reports'][0]['title']}")
```

### Download all PDFs for a specific year

```python
docs = await execute({
    "function": "get_document_urls",
    "year": 2024,
    "document_type": "PDF"
})

for doc in docs['documents']:
    print(f"Download: {doc['title']} - {doc['url']}")
```

## Data Source

- **Website**: https://www.rbi.com/English/investors/annual-reports/default.aspx
- **Company**: Restaurant Brands International Inc. (NYSE: QSR)
- **Brands**: Burger King, Tim Hortons, Popeyes, Firehouse Subs