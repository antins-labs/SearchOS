# SSE (上海证券交易所) API Access Skill

This skill provides programmatic access to Shanghai Stock Exchange (SSE) IPO and financial data through their public JSONP API at `query.sse.com.cn`.

## Features

### 1. IPO Inquiry Information (`get_ipo_inquiry_info`)

Get detailed IPO pricing and inquiry data for a specific security, including:
- Offline/online investor participation counts
- Median and weighted average bid prices
- Issue price and P/E ratio
- Allocation details

**Example:**
```python
{
    "function": "get_ipo_inquiry_info",
    "security_code": "688710"
}
```

**Returns:**
- `SECURITY_CODE`: Security code
- `SECURITY_NAME`: Company name
- `ISSUE_PRICE`: Issue price
- `ISSUANCE_PRICE_EARNINGS_RATIO`: P/E ratio
- `OFFLINE_INVESTOR_OBJECT`: Number of offline investors
- `OFFLINE_PLACING_OBJECT`: Number of placing objects
- `MEDIAN_PRICE_AFTER/BELFRE`: Median bid prices
- `WEIGHTED_AVG_PRICE_AFTER/BEF`: Weighted average prices
- `ALLOTMENT_SHARES`: Allocated shares

### 2. IPO Process Status (`get_ipo_process_status`)

Get the complete IPO timeline and process status for a security.

**Example:**
```python
{
    "function": "get_ipo_process_status",
    "security_code": "688710"
}
```

**Returns:**
- `IPO_NOTICE_DATE`: IPO announcement date
- `INQUIRY_DATE`: Inquiry period dates
- `ONLINE_ROADSHOW_DATE`: Online roadshow date
- `ISSUANCE_ANNOUNCEMENT_DATE`: Issuance announcement date
- `ONLINE_ISSUANCE_DATE`: Online issuance date
- `ANNOUNCE_SUCCESS_RATE_DATE`: Win rate announcement date
- `PAYMENT_START/END_DATE`: Payment dates
- `LISTED_DATE`: Listing date

### 3. IPO List (`get_ipo_list`)

Get a paginated list of IPOs, filterable by board type.

**Example:**
```python
{
    "function": "get_ipo_list",
    "stock_type": "2",    # "" = all, "0" = main board, "2" = STAR market
    "page": 1,
    "page_size": 20
}
```

**Returns:**
- Paginated list of IPOs with details like issue price, lot winning rate, subscription dates

### 4. Financing Information (`get_financing_info`)

Get company financing history including IPO and additional share issuance.

**Example:**
```python
{
    "function": "get_financing_info",
    "company_code": "688710",
    "list_board": "2"     # "1" = main board, "2" = STAR market
}
```

**Returns:**
- `ipo_data`: IPO financing records
- `additional_issuance_data`: Additional issuance records
- Fields include issue volume, price, date, raised capital, P/E ratio, issuance method

### 5. Dividend Information (`get_dividend_info`)

Get dividend history for a company.

**Example:**
```python
{
    "function": "get_dividend_info",
    "company_code": "688710",
    "is_star": "1"        # "1" = STAR market, "" = others
}
```

**Returns:**
- Record date, ex-dividend date
- Dividend per share
- Total dividend amount
- Share capital details

### 6. Rights Issue Information (`get_rights_issue_info`)

Get rights issue (配股) information for a company.

**Example:**
```python
{
    "function": "get_rights_issue_info",
    "company_code": "688710",
    "list_board": "2"
}
```

## Data Source

All data is fetched from the Shanghai Stock Exchange's public API:
- **Endpoint**: `https://query.sse.com.cn/commonQuery.do`
- **Format**: JSONP (JSON with Padding)
- **Method**: GET requests with specific `sqlId` parameters

## Parameter Types

### Stock/Board Types
- `stock_type` for IPO list:
  - `""` - All stocks
  - `"0"` - Main Board (主板)
  - `"2"` - STAR Market (科创板)

### Listing Board
- `list_board` for financing/rights issue:
  - `"1"` - Main Board
  - `"2"` - STAR Market

### STAR Market Flag
- `is_star` for dividend info:
  - `"1"` - STAR Market company
  - `""` - Non-STAR Market company

## Error Handling

Functions return an `error` key in the response dictionary when issues occur:
- Missing required parameters
- API request failures
- JSON parsing errors

## Example Usage

```python
# Get IPO inquiry info for 益诺思 (688710)
result = await execute({
    "function": "get_ipo_inquiry_info",
    "security_code": "688710"
})

# Get STAR Market IPOs (first 10)
result = await execute({
    "function": "get_ipo_list",
    "stock_type": "2",
    "page": 1,
    "page_size": 10
})

# Get dividend history
result = await execute({
    "function": "get_dividend_info",
    "company_code": "688710"
})
```

## Notes

1. **Security/Company Codes**: Use 6-digit codes (e.g., "688710", "600000")
2. **STAR Market**: Securities starting with "688" are listed on the STAR Market (科创板)
3. **Data Availability**: Historical data availability varies by company and listing date
4. **Rate Limiting**: The API does not appear to have strict rate limits, but reasonable usage is encouraged
5. **Chinese Field Names**: Many returned field names are in Chinese pinyin or abbreviations