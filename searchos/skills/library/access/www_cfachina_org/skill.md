# China Futures Association - Monthly Transaction Data

## Overview

This skill provides programmatic access to the China Futures Association (CFA) monthly transaction statistics from www.cfachina.org. The CFA publishes comprehensive monthly reports on China's futures market trading activities, including data from:

- Shanghai Futures Exchange (SHFE)
- Shanghai International Energy Exchange (INE)
- Zhengzhou Commodity Exchange (ZCE)
- Dalian Commodity Exchange (DCE)
- China Financial Futures Exchange (CFFEX)
- Guangzhou Futures Exchange (GFEX)

## Available Functions

### 1. `list_reports` - List Available Monthly Reports

Lists the available monthly transaction reports with pagination support.

**Parameters:**
- `page` (integer, optional): Page number, 1-indexed. Default: 1
- `max_pages` (integer, optional): Number of pages to fetch. Default: 1, Max: 10

**Example:**
```python
result = await execute({
    'function': 'list_reports',
    'page': 1,
    'max_pages': 2
})
```

**Returns:**
- `reports`: Array of report objects with `title`, `url`, and `path`
- `pages_fetched`: Number of pages retrieved
- `error`: Error message if any

### 2. `get_report` - Get Report Details

Retrieves details of a specific monthly report including the summary text and Excel download link.

**Parameters:**
- `url` (string): Full URL of the report page, OR
- `report_id` (string): Report ID like "202506/t20250611_80854"

**Example:**
```python
result = await execute({
    'function': 'get_report',
    'report_id': '202506/t20250611_80854'
})
```

**Returns:**
- `title`: Report title (e.g., "2025年5月全国期货市场交易情况")
- `date`: Publication date
- `content`: Array of summary paragraphs
- `excel_url`: Direct download URL for the Excel file
- `excel_name`: Excel file name
- `error`: Error message if any

### 3. `download_excel` - Download and Parse Excel Data

Downloads and parses the Excel file containing detailed transaction statistics.

**Parameters:**
- `url` (string): Direct URL to Excel file, OR
- `report_url` (string): Report page URL (will extract Excel URL)
- `month` (integer, optional): Month number (1-12) to extract specific sheet

**Example:**
```python
# Download all sheets
result = await execute({
    'function': 'download_excel',
    'report_url': 'https://www.cfachina.org/servicesupport/researchandpublishin/statisticalsdata/monthlytransactiondata/202506/t20250611_80854.html'
})

# Download specific month sheet
result = await execute({
    'function': 'download_excel',
    'url': 'https://www.cfachina.org/servicesupport/researchandpublishin/statisticalsdata/monthlytransactiondata/202506/P020250611501774429093.xlsx',
    'month': 5
})
```

**Returns:**
- `sheets`: List of sheet names ("1月" through "12月")
- `data`: Dictionary keyed by sheet name containing:
  - `info`: Year/month info
  - `row_count`: Number of data rows
  - `rows`: Array of row dictionaries with column data
- `error`: Error message if any

### 4. `search_reports` - Search Reports by Year/Month

Searches for reports matching specific year and/or month criteria.

**Parameters:**
- `year` (integer): Year to filter (e.g., 2025)
- `month` (integer): Month to filter (1-12)
- `max_results` (integer, optional): Maximum results to return. Default: 50

**Example:**
```python
result = await execute({
    'function': 'search_reports',
    'year': 2025,
    'month': 5
})
```

**Returns:**
- `reports`: Array of matching report objects
- `total_found`: Total number of matches
- `error`: Error message if any

## Excel Data Structure

Each Excel file contains 12 sheets (one per month) with the following data for each futures contract:

**Columns include:**
- 交易所名称 (Exchange Name)
- 品种名称 (Product Name)
- 本月成交量（手）(Current Month Volume - lots)
- 去年同期成交量（手）(Same Period Last Year Volume)
- 同比增减（％）(Year-over-Year Change %)
- 上月成交量（手）(Last Month Volume)
- 环比增减（％）(Month-over-Month Change %)
- 本月成交量占全国份额（％）(National Market Share %)
- 本月成交额（亿元）(Current Month Turnover - 100M CNY)
- And additional metrics for turnover, cumulative totals, and open interest

## Data Coverage

- **Historical Depth**: Reports available from multiple years
- **Update Frequency**: Monthly publication
- **Exchanges Covered**: All 6 major futures exchanges in China
- **Products**: All actively traded futures contracts

## Notes

- The website is in Chinese, but data field names are preserved as-is
- Excel files are in XLSX format with multiple monthly sheets
- Rate limiting: The skill includes built-in delays between requests to be respectful to the server
- If you need specific data analysis, use the `download_excel` function to get structured data that can be further processed

## Error Handling

All functions return an `error` field when issues occur. Check this field in the response to handle errors gracefully:

```python
result = await execute({'function': 'get_report', 'url': '...'})
if result.get('error'):
    print(f"Error: {result['error']}")
else:
    # Process successful result
    print(f"Title: {result['title']}")
```

## Typical Usage Workflow

1. **List or search for reports** to find the one you need
2. **Get report details** to see the summary and get the Excel download URL
3. **Download and parse Excel data** for detailed analysis by product/exchange

## Example: Complete Workflow

```python
# Step 1: Find May 2025 report
search_result = await execute({
    'function': 'search_reports',
    'year': 2025,
    'month': 5
})

if search_result['reports']:
    report = search_result['reports'][0]
    
    # Step 2: Get report details
    report_detail = await execute({
        'function': 'get_report',
        'url': report['url']
    })
    
    # Step 3: Download Excel with May data
    excel_data = await execute({
        'function': 'download_excel',
        'url': report_detail['excel_url'],
        'month': 5
    })
    
    # Analyze the data
    for sheet_name, sheet_data in excel_data['data'].items():
        print(f"{sheet_name}: {sheet_data['row_count']} rows")
```