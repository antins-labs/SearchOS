# eBay Investor Relations Financial Data

Access detailed financial information from eBay Inc.'s investor relations website including quarterly earnings reports, annual reports, and parsed financial statements.

## Features

### 1. Financial Reports (`get_financial_reports`)

Retrieve a list of eBay's financial reports including quarterly earnings and annual reports. Each report includes downloadable documents such as:
- Press releases (PDF)
- Form 10-Q / 10-K filings
- Earnings presentations
- Webcast links

**Parameters:**
- `year` (optional): Filter by year (e.g., 2025)
- `report_type` (optional): 'quarterly' or 'annual'
- `limit` (optional): Maximum results (default: 20)

**Example:**
```python
# Get all Q4 reports from 2024
execute({
    "function": "get_financial_reports",
    "report_type": "quarterly",
    "year": 2024
})
```

### 2. Quarterly Earnings (`get_quarterly_earnings`)

Get quarterly earnings press releases with automatically parsed financial tables. Extracts:
- Income statement data (revenue, net income, EPS)
- Balance sheet summaries
- Forward guidance
- Key financial figures

**Parameters:**
- `quarters` (optional): Number of recent quarters (default: 4)
- `include_tables` (optional): Include parsed table data (default: 'true')

**Example:**
```python
# Get last 2 quarters with full table data
execute({
    "function": "get_quarterly_earnings",
    "quarters": 2,
    "include_tables": "true"
})
```

### 3. Parse Financial Statement (`parse_financial_statement`)

Extract specific financial statements from a particular quarter with structured data:
- **Income Statement**: Revenue, operating income, net income, EPS (GAAP & non-GAAP)
- **Balance Sheet**: Assets, liabilities, stockholders' equity
- **Guidance**: Revenue and EPS guidance for upcoming quarter

**Parameters:**
- `quarter` (optional): Quarter to parse ('Q1', 'First Quarter', 'first', etc.)
- `year` (optional): Year (e.g., 2025)
- `statement_type` (optional): 'income', 'balance', 'guidance', or 'all' (default)

**Example:**
```python
# Get Q1 2025 income statement
execute({
    "function": "parse_financial_statement",
    "quarter": "Q1",
    "year": 2025,
    "statement_type": "income"
})
```

## Data Structure

### Financial Reports Response
```json
{
  "total_returned": 4,
  "reports": [
    {
      "title": "First Quarter 2025",
      "year": 2025,
      "type": "First Quarter",
      "documents": [
        {
          "title": "Press Release",
          "type": "PDF",
          "size": "165 KB",
          "category": "news",
          "url": "https://ebay.q4cdn.com/..."
        }
      ]
    }
  ]
}
```

### Quarterly Earnings Response
```json
{
  "total_returned": 1,
  "quarterly_earnings": [
    {
      "headline": "eBay Inc. Reports First Quarter 2025 Results",
      "date": "04/30/2025 16:05:00",
      "table_count": 13,
      "key_figures": {
        "revenue": "$2,585",
        "net_income": "$501",
        "gaap_eps": "$1.05",
        "non_gaap_eps": "$1.37"
      },
      "tables": {
        "income_statement": [...],
        "balance_sheet": [...],
        "guidance": [...]
      }
    }
  ]
}
```

## Notes

- Data is sourced directly from eBay's investor relations API
- Financial figures are extracted from HTML tables in press releases
- All monetary values are in millions or billions as noted in the source
- Non-GAAP measures are clearly labeled in the extracted data
- API has rate limiting; heavy usage may require delays between requests