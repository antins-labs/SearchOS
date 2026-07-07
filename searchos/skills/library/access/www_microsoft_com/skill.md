# Microsoft Investor Relations Access Skill

This skill provides programmatic access to Microsoft's investor relations data, including annual reports, quarterly earnings, and stock information.

## Overview

Microsoft's Investor Relations website (`www.microsoft.com/en-us/investor`) contains a wealth of financial information that is publicly accessible but requires parsing HTML pages. This skill extracts structured data from those pages and returns it in a JSON format.

## Functions

### 1. `annual_reports`

List all available Microsoft annual reports from 1996 to present.

**Parameters:** None

**Returns:**
```json
{
  "success": true,
  "count": 30,
  "annual_reports": [
    {
      "year": 2025,
      "view_url": "https://www.microsoft.com/investor/reports/ar25/index.html",
      "download_url": "https://www.microsoft.com/investor/reports/ar25/download-center/"
    },
    ...
  ]
}
```

### 2. `annual_report_detail`

Get details for a specific annual report year.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| year | integer | Yes | The annual report year (e.g., 2024, 2023) |

**Returns:**
```json
{
  "success": true,
  "year": 2024,
  "title": "Microsoft 2024 Annual Report",
  "view_url": "https://www.microsoft.com/investor/reports/ar24/index.html",
  "download_url": "https://www.microsoft.com/investor/reports/ar24/download-center/",
  "downloads": [...]
}
```

### 3. `earnings`

Get detailed earnings data for a specific fiscal year and quarter.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| fiscal_year | integer | Yes | The fiscal year (e.g., 2025, 2026) |
| quarter | integer | Yes | The quarter (1-4) |
| section | string | No | The specific section (default: "press-release-webcast") |

**Sections:**
- `press-release-webcast` - Earnings press release and summary
- `income-statements` - Revenue, costs, gross margin, operating income, net income, EPS
- `comprehensive-income` - Comprehensive income statement
- `balance-sheets` - Assets, liabilities, equity
- `cash-flows` - Operating, investing, financing activities
- `segment-revenues` - Revenue by business segment
- `performance` - Performance metrics
- `metrics` - Key metrics (Cloud revenue, Azure growth, bookings, etc.)
- `productivity-and-business-processes-performance` - M365, LinkedIn, Dynamics
- `intelligent-cloud-performance` - Azure, server products
- `more-personal-computing-performance` - Windows, Gaming, Devices

**Returns:**
```json
{
  "success": true,
  "fiscal_year": 2026,
  "quarter": 3,
  "section": "income-statements",
  "url": "https://www.microsoft.com/en-us/Investor/earnings/FY-2026-Q3/income-statements",
  "title": "FY26 Q3 - Income Statements - Investor Relations - Microsoft",
  "tables": [...],
  "tables_formatted": [...]
}
```

### 4. `current_quarter`

Get information about Microsoft's current fiscal year and quarter.

**Parameters:** None

**Returns:**
```json
{
  "success": true,
  "current_fiscal_year": 2026,
  "current_quarter": 3,
  "note": "Microsoft's fiscal year starts in July. Q1: Jul-Sep, Q2: Oct-Dec, Q3: Jan-Mar, Q4: Apr-Jun"
}
```

### 5. `latest_earnings`

Automatically find and return the most recent available earnings data.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| section | string | No | The earnings section to retrieve (default: "press-release-webcast") |

**Returns:** Same format as `earnings` function, with `is_latest: true` added.

### 6. `list_earnings_sections`

List all available sections for a specific quarter.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| fiscal_year | integer | Yes | The fiscal year |
| quarter | integer | Yes | The quarter (1-4) |

**Returns:**
```json
{
  "success": true,
  "fiscal_year": 2026,
  "quarter": 3,
  "sections": [
    {
      "name": "press-release-webcast",
      "description": "Press release and webcast information",
      "url": "https://..."
    },
    ...
  ]
}
```

### 7. `stock_quote`

Get the current Microsoft (MSFT) stock quote.

**Parameters:** None

**Returns:**
```json
{
  "success": true,
  "symbol": "MSFT",
  "company_name": "Microsoft Corporation",
  "price": 379.4,
  "price_change": 0.49,
  "price_change_percent": 0.13,
  "price_open": 377.82,
  "price_high": 381.37,
  "price_low": 373.28,
  "price_previous_close": 378.91,
  "volume": 59714157,
  "average_volume": 36808904,
  "market_cap": 2818348239000,
  "pe_ratio": 22.60,
  "fifty_two_week_high": 555.45,
  "fifty_two_week_low": 356.28,
  "dividend_yield_percent": 0.96,
  "exchange": "Nasdaq Stock Market",
  "currency": "USD",
  "last_updated": "2026-06-18T23:59:58.864Z"
}
```

## Examples

### Get latest earnings press release
```python
result = await execute({
    "function": "latest_earnings",
    "section": "press-release-webcast"
})
```

### Get Q3 FY2026 income statement
```python
result = await execute({
    "function": "earnings",
    "fiscal_year": 2026,
    "quarter": 3,
    "section": "income-statements"
})
```

### Get key business metrics
```python
result = await execute({
    "function": "earnings",
    "fiscal_year": 2026,
    "quarter": 3,
    "section": "metrics"
})
```

### Get annual reports list
```python
result = await execute({
    "function": "annual_reports"
})
```

### Get current stock price
```python
result = await execute({
    "function": "stock_quote"
})
```

## Microsoft Fiscal Year

Microsoft's fiscal year differs from the calendar year:

| Quarter | Months | Calendar Year Position |
|---------|--------|----------------------|
| Q1 | Jul, Aug, Sep | Calendar Q3 |
| Q2 | Oct, Nov, Dec | Calendar Q4 |
| Q3 | Jan, Feb, Mar | Calendar Q1 |
| Q4 | Apr, May, Jun | Calendar Q2 |

For example, "FY2026 Q3" refers to January-March 2026.

## Data Available

### Annual Reports
- **Years Available**: 1996 - Present
- **Types**: View online (HTML) and download center (PDFs)

### Earnings Data
- **Fiscal Quarters**: Available going back multiple years
- **Financial Statements**: Income statement, balance sheet, cash flows
- **Segments**: Productivity & Business Processes, Intelligent Cloud, More Personal Computing
- **Key Metrics**:
  - Revenue by product/service
  - Microsoft Cloud revenue
  - Azure growth rate
  - Commercial bookings
  - 365 Commercial seat growth
  - LinkedIn revenue growth
  - Gaming/Xbox revenue

## Technical Notes

1. **No API Key Required**: All data is publicly available on Microsoft's investor website
2. **HTML Parsing**: Data is extracted from HTML tables using BeautifulSoup
3. **Rate Limiting**: Be respectful of frequency; avoid rapid successive calls
4. **Data Freshness**:
   - Stock quotes are near real-time
   - Earnings data is updated quarterly
   - Annual reports are published once per year

## Error Handling

All functions return a dictionary with:
- `success: true` on success, along with data
- `error: "message"` on failure (no exception thrown for user errors)

Common errors:
- `Missing required parameter: function`
- `Missing required parameters: fiscal_year and quarter`
- `Invalid section. Must be one of: ...`
- `Earnings data not found for FY-XXXX-QX`
- `Annual report for year XXXX not found`