# Amazon Investor Relations Access Skill

Access investor relations data from Amazon's official investor relations website (ir.aboutamazon.com), including SEC filings, press releases, events, and stock information.

## Overview

This skill provides programmatic access to Amazon's investor relations data through their Q4 Inc. platform API. The site uses Cloudflare protection, so this skill utilizes Playwright to capture the JSON API responses that power the dynamic listings.

**Base URL:** https://ir.aboutamazon.com

## Available Functions

### 1. `get_sec_filings`

Retrieve SEC filing documents (10-K, 10-Q, 8-K, etc.) for Amazon.

**Parameters:**
- `year` (optional): Year to filter (e.g., 2025). Default: most recent year
- `page_size` (optional): Number of results. Default: -1 (all results). Note: API may return all results regardless
- `page_number` (optional): Page number, 0-indexed. Default: 0

**Returns:** List of SEC filings with:
- Filing type (Form 10-K, 10-Q, 8-K, etc.)
- Filing date and description
- Document list with PDF, XBRL, Excel URLs
- Filing agent information

**Example:**
```python
{
    "function": "get_sec_filings",
    "year": 2025
}
```

### 2. `get_sec_filing_years`

Get list of available years for SEC filings.

**Parameters:** None

**Returns:** List of years with available SEC filings (e.g., [2026, 2025, 2024, ..., 1997])

**Example:**
```python
{
    "function": "get_sec_filing_years"
}
```

### 3. `get_press_releases`

Retrieve press releases from Amazon IR.

**Parameters:**
- `year` (optional): Year filter. Default: -1 (all years)
- `page_size` (optional): Number of results. Default: 10
- `page_number` (optional): Page number, 0-indexed. Default: 0
- `tag` (optional): Tag filter. Default: "home"

**Returns:** List of press releases with:
- Headline and short description
- Publication date
- Link to full article
- Media files and thumbnails

**Example:**
```python
{
    "function": "get_press_releases",
    "year": 2026,
    "page_size": 5
}
```

### 4. `get_events`

Retrieve investor events such as earnings calls, presentations, and conferences.

**Parameters:**
- `year` (optional): Year filter. Default: -1 (all years)
- `page_size` (optional): Number of results. Default: 20
- `page_number` (optional): Page number, 0-indexed. Default: 0

**Returns:** List of events with:
- Event title and type
- Event date and time
- Presentation materials and webcast links

**Example:**
```python
{
    "function": "get_events",
    "year": 2025
}
```

### 5. `get_event_years`

Get list of available years for events.

**Parameters:** None

**Returns:** List of years with available events

**Example:**
```python
{
    "function": "get_event_years"
}
```

### 6. `get_stock_quote`

Get current stock quote for Amazon (AMZN).

**Parameters:** None

**Returns:** Stock quote data including:
- Current price and change
- Day's high/low
- 52-week high/low
- Volume
- Previous close
- Company name and ticker

**Example:**
```python
{
    "function": "get_stock_quote"
}
```

## Response Format

All functions return a dictionary with the following structure:

```python
{
    "success": True/False,
    "data": [...],  # The actual data (list or dict)
    "error": None or "error message"
}
```

## Data Fields

### SEC Filing
- `FilingTypeMnemonic`: Form type (e.g., "10-K", "8-K")
- `FilingDate`: Date filed (MM/DD/YYYY HH:MM:SS)
- `FilingDescription`: Description of the filing
- `DocumentList`: List of available documents (PDF, XBRL, XLS, HTML)
- `PdfUrl`: Direct URL to PDF document
- `LinkToDetailPage`: Path to detail page on IR site

### Press Release
- `Headline`: Title of the press release
- `PressReleaseDate`: Publication date
- `ShortBody`: Summary text
- `LinkToDetailPage`: Path to full article
- `MediaFiles`: Associated images/media

### Stock Quote
- `TradePrice`: Current price
- `Change`: Dollar change
- `PercChange`: Percentage change
- `High`/`Low`: Day's range
- `High52`/`Low52`: 52-week range
- `Volume`: Trading volume
- `TradeDate`: Date/time of quote

## Technical Notes

- **Cloudflare Protection**: The site uses Cloudflare protection, so Playwright is used to bypass it and capture API responses
- **Response Time**: Each API call may take 2-5 seconds due to browser automation
- **Data Freshness**: SEC filings are updated in real-time from EDGAR; stock quotes have a 15-20 minute delay
- **Date Format**: All dates are in US Eastern Time (MM/DD/YYYY HH:MM:SS)
- **API Key**: The embedded API key (BF185719B0464B3CB809D23926182246) is from the site's JavaScript
- **Pagination**: The SEC filings API may return all results regardless of page_size parameter

## Use Cases

1. **Financial Research**: Fetch recent 10-K and 10-Q filings for analysis
2. **News Monitoring**: Track press releases for product announcements and earnings
3. **Event Tracking**: Get dates and materials for earnings calls and investor presentations
4. **Market Data**: Retrieve current stock price and trading information
5. **Historical Analysis**: Access years of SEC filings for trend analysis

## Limitations

- The site uses Cloudflare protection which adds overhead to each request
- Some API endpoints may return empty results depending on data availability
- The pagination parameters may not always work as expected on certain endpoints
- Stock quote data has a 15-20 minute delay