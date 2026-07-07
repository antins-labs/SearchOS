# Apple Investor Relations Access Skill

Access Apple's comprehensive investor relations data through their Q4 Inc. platform APIs.

## Overview

This skill provides structured access to Apple's investor relations information, including:
- **Financial Reports**: Quarterly earnings reports and annual reports with downloadable documents
- **SEC Filings**: All SEC filings (10-K, 10-Q, 8-K, Form 4, etc.) dating back to 1994
- **Stock Data**: Current quotes (20-minute delayed) and historical prices
- **Events**: Earnings calls, investor presentations, and press releases
- **Additional Reports**: Supplementary financial documents

## Available Functions

### Financial Reports

#### `get_financial_reports`
Retrieve quarterly or annual financial reports with associated documents.

**Parameters:**
- `report_type` (string): `"quarterly"` or `"annual"` (default: `"quarterly"`)
- `year` (integer): Filter by year, -1 for all years (default: -1)
- `page_size` (integer): Results per page, -1 for all (default: 50)
- `page_number` (integer): Page number (default: 0)

**Returns:** List of reports with documents (press releases, financial statements, 10-K/10-Q filings)

**Example:**
```python
result = await execute({
    "function": "get_financial_reports",
    "report_type": "annual",
    "year": 2025
})
```

#### `get_financial_report_years`
Get available years for financial reports.

**Parameters:**
- `report_type` (string): `"quarterly"` or `"annual"` (default: `"annual"`)

### SEC Filings

#### `get_sec_filings`
Retrieve SEC filings with downloadable documents (PDF, Excel, HTML).

**Parameters:**
- `year` (integer): Filter by year, -1 for all (default: -1)
- `filing_type` (string): Filter by type (e.g., `"10-K"`, `"10-Q"`, `"8-K"`, `"4"`) (default: all)
- `page_size` (integer): Results per page (default: 50)
- `page_number` (integer): Page number (default: 0)

**Returns:** List of filings with metadata and document links

**Common filing types:**
- `10-K`: Annual report
- `10-Q`: Quarterly report
- `8-K`: Current report
- `4`: Insider trading statement
- `SD`: Specialized disclosure
- `144`: Proposed sale of securities

**Example:**
```python
result = await execute({
    "function": "get_sec_filings",
    "year": 2025,
    "filing_type": "10-K"
})
```

#### `get_sec_filing_years`
Get available years for SEC filings (1994 to present).

### Stock Data

#### `get_stock_quote`
Get current AAPL stock quote.

**Returns:** Quote with price, change, volume, 52-week high/low, etc.

**Note:** Quotes are delayed by 20 minutes.

**Example:**
```python
result = await execute({"function": "get_stock_quote"})
# Returns: {price: 298.01, change: 2.06, percent_change: 0.696, ...}
```

#### `get_stock_history`
Get historical daily stock prices.

**Parameters:**
- `days` (integer): Number of trading days (default: 30, max: 3000)

**Returns:** List of daily OHLCV data

**Example:**
```python
result = await execute({
    "function": "get_stock_history",
    "days": 90
})
```

### Events

#### `get_events`
Get investor events (earnings calls, presentations, press releases).

**Parameters:**
- `year` (integer): Filter by year, -1 for all (default: -1)
- `include_financial_reports` (boolean): Include financial report events (default: true)
- `include_presentations` (boolean): Include presentations (default: true)
- `include_press_releases` (boolean): Include press releases (default: true)
- `page_size` (integer): Results per page (default: 20)
- `page_number` (integer): Page number (default: 0)

**Returns:** List of events with dates, webcast links, and attachments

**Example:**
```python
result = await execute({
    "function": "get_events",
    "year": 2025
})
```

#### `get_event_years`
Get available years for investor events.

### Additional Reports

#### `get_additional_reports`
Get supplementary financial documents.

**Parameters:**
- `year` (integer): Filter by year, -1 for all (default: -1)

**Returns:** List of additional reports with file links

## Technical Details

### API Architecture

Apple uses Q4 Inc.'s investor relations platform, which exposes SOAP-style `.svc` endpoints:
- `FinancialReport.svc` - Financial reports
- `SECFiling.svc` - SEC filings
- `StockQuote.svc` - Stock data
- `Event.svc` - Investor events
- `ContentAsset.svc` - Additional content

### Cloudflare Protection

The site is protected by Cloudflare, requiring browser automation to establish a valid session. This skill uses Playwright to:
1. Navigate to the main investor page
2. Establish session cookies
3. Execute JavaScript fetch calls from within the browser context

### Data Freshness

- **Stock quotes**: 20-minute delayed
- **SEC filings**: Updated in near real-time after SEC acceptance
- **Financial reports**: Published after each earnings release
- **Historical stock data**: Updated daily after market close

## Response Format

All functions return a consistent structure:

```python
{
    "success": True,  # Boolean indicating success
    "count": 10,      # Number of items returned (when applicable)
    "data": [...]     # The requested data
}
```

On error:
```python
{
    "success": False,
    "error": "Description of the error"
}
```

## Document URLs

Documents (PDFs, Excel files) are hosted on:
- `https://s2.q4cdn.com/470004039/...` - Q4 CDN for filings
- `https://d18rn0p25nwr6d.cloudfront.net/CIK-...` - CloudFront for SEC documents
- `https://www.apple.com/newsroom/...` - Apple's newsroom for press releases

All document URLs are direct download links requiring no authentication.

## Example Usage

### Get latest quarterly earnings
```python
result = await execute({
    "function": "get_financial_reports",
    "report_type": "quarterly",
    "page_size": 1
})
```

### Get all 10-K filings from 2024
```python
result = await execute({
    "function": "get_sec_filings",
    "year": 2024,
    "filing_type": "10-K"
})
```

### Get stock performance for last quarter
```python
result = await execute({
    "function": "get_stock_history",
    "days": 63  # ~3 months of trading days
})
```

### Get upcoming earnings events
```python
result = await execute({
    "function": "get_events",
    "include_presentations": false,
    "include_press_releases": false,
    "page_size": 5
})
```