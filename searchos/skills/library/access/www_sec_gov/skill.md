# SEC EDGAR Access Skill

Access structured financial data from SEC EDGAR filings.

## Overview

This skill provides programmatic access to the U.S. Securities and Exchange Commission's EDGAR database, enabling:

- **Company lookup** by ticker symbol or company name
- **Filing retrieval** with automatic table extraction
- **XBRL financial data** extraction for structured analysis
- **Historical financial concepts** with full time series

## Important Requirements

SEC.gov requires automated tools to identify themselves. Include contact information in the `user_agent` parameter:

```
user_agent: "YourApp contact@youremail.com"
```

Default rate limit: 10 requests per second.

## Functions

### Company Lookup

#### Get Company by Ticker
```python
result = await execute({
    "function": "get_company_by_ticker",
    "ticker": "AAPL"
})
```

Returns:
```json
{
  "cik": "320193",
  "cik_padded": "0000320193",
  "ticker": "AAPL",
  "name": "Apple Inc.",
  "status": "found"
}
```

#### Search for Company
```python
result = await execute({
    "function": "get_cik_lookup",
    "query": "upstream"
})
```

### Company Information

#### Get Company Details
```python
result = await execute({
    "function": "get_company_info",
    "cik": "2022626"
})
```

Returns company name, ticker, SIC code, state of incorporation, and recent filings with direct URLs.

#### Get Filings by Type
```python
# Get most recent 10-K filings
result = await execute({
    "function": "get_filings_by_type",
    "cik": "2022626",
    "form_type": "10-K",
    "limit": 5
})
```

Common form types:
- `10-K`: Annual report
- `10-Q`: Quarterly report
- `8-K`: Current report/material events
- `DEF 14A`: Proxy statement
- `4`: Insider trading
- `S-1`: IPO registration
- `424B4`: Prospectus

### Financial Data (XBRL)

#### Get Available XBRL Concepts
```python
result = await execute({
    "function": "get_company_facts",
    "cik": "2022626"
})
```

Returns available taxonomies (us-gaap, dei) and concept names.

#### Get Key Financial Metrics
```python
result = await execute({
    "function": "get_financial_data",
    "cik": "2022626"
})
```

Extracts common metrics:
- Balance sheet: Assets, Liabilities, Stockholders' Equity, Cash
- Income: Revenue, Net Income, Operating Income, R&D Expense
- Per share: EPS (basic/diluted), Shares Outstanding

With custom concepts:
```python
result = await execute({
    "function": "get_financial_data",
    "cik": "2022626",
    "concepts": ["Assets", "NetIncomeLoss", "StockholdersEquity"]
})
```

#### Get Concept History
```python
# Get revenue history
result = await execute({
    "function": "get_concept_history",
    "cik": "320193",  # Apple
    "concept": "RevenueFromContractWithCustomerExcludingAssessedTax"
})
```

Common XBRL concepts:
- `Assets`, `AssetsCurrent`, `AssetsNoncurrent`
- `Liabilities`, `LiabilitiesCurrent`, `LiabilitiesNoncurrent`
- `StockholdersEquity`
- `CashAndCashEquivalentsAtCarryingValue`
- `RevenueFromContractWithCustomerExcludingAssessedTax`
- `NetIncomeLoss`
- `OperatingIncomeLoss`
- `ResearchAndDevelopmentExpense`
- `EarningsPerShareBasic`, `EarningsPerShareDiluted`
- `CommonStockSharesOutstanding`

### Filing Documents

#### Fetch Filing with Table Extraction
```python
result = await execute({
    "function": "get_filing_document",
    "url": "https://www.sec.gov/Archives/edgar/data/2022626/000119312524236714/d843142d424b4.htm"
})
```

Returns:
- Document metadata (title, type, length)
- Detected sections (business, risk factors, MD&A, financial statements)
- Extracted financial tables with row/column structure

#### Parse Filing URL
```python
result = await execute({
    "function": "parse_filing_url",
    "url": "https://www.sec.gov/Archives/edgar/data/2022626/000119312524236714/d843142d424b4.htm"
})
```

Returns CIK, accession number, and document name.

## Examples

### Complete Company Analysis

```python
# 1. Look up company by ticker
company = await execute({
    "function": "get_company_by_ticker",
    "ticker": "UPB"
})
cik = company["cik"]

# 2. Get company details
info = await execute({
    "function": "get_company_info",
    "cik": cik
})
print(f"Company: {info['name']}")
print(f"SIC: {info['sic_description']}")

# 3. Get financial metrics
financials = await execute({
    "function": "get_financial_data",
    "cik": cik
})
for concept, data in financials["extracted_facts"].items():
    latest = data["values"][-1] if data["values"] else None
    if latest:
        print(f"{concept}: {latest['val']} ({latest['end']})")

# 4. Get latest 10-K
filings = await execute({
    "function": "get_filings_by_type",
    "cik": cik,
    "form_type": "10-K",
    "limit": 1
})
if filings["filings"]:
    doc = await execute({
        "function": "get_filing_document",
        "url": filings["filings"][0]["filing_url"]
    })
    print(f"Found {doc['financial_table_count']} financial tables")
```

### Revenue History Comparison

```python
companies = ["AAPL", "MSFT", "GOOGL"]
for ticker in companies:
    # Get CIK
    company = await execute({
        "function": "get_company_by_ticker",
        "ticker": ticker
    })
    
    # Get revenue history
    history = await execute({
        "function": "get_concept_history",
        "cik": company["cik"],
        "concept": "RevenueFromContractWithCustomerExcludingAssessedTax"
    })
    
    if "units" in history and "USD" in history["units"]:
        print(f"\n{ticker} Revenue History:")
        for val in history["units"]["USD"][:5]:
            print(f"  {val['end']}: ${val['val']:,}")
```

## Response Structure

All functions return a dictionary with:
- `status`: "success", "not_found", or "error"
- `error`: Error message if applicable
- Function-specific data fields

## Error Handling

The skill returns errors in the response rather than raising exceptions:

```python
result = await execute({"function": "get_company_by_ticker", "ticker": "INVALID"})
if result.get("status") == "not_found":
    print(f"Ticker not found: {result.get('error')}")
```

## Notes

- SEC User-Agent requirement: Include your app name and contact email
- Filing documents can be large (millions of characters); the skill extracts key tables
- XBRL data availability depends on what the company has filed
- Some older filings may not have XBRL data available