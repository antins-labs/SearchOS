# Chinese Ministry of Finance - Central Transfer Payments Table Extractor

This skill extracts financial budget tables (决算表) from the Chinese Ministry of Finance website (yss.mof.gov.cn), specifically focusing on central government transfer payments to local governments.

## Overview

The website hosts government financial data in static HTML pages with embedded tables. These tables contain:
- Central to local government transfer payment budgets and final accounts
- Regional breakdowns of transfer payments
- Hierarchical category structures for budget items

## Supported Table Types

### 1. Summary Tables (决算表)
Example: `2021年中央对地方转移支付决算表`

Contains hierarchical budget categories:
```
一、一般性转移支付 (General Transfer Payments)
  均衡性转移支付 (Balanced Transfer Payments)
  重点生态功能区转移支付 (Key Ecological Areas Transfer Payments)
  ...
二、专项转移支付 (Special Transfer Payments)
  ...
```

### 2. Regional Tables (分地区决算表)
Example: `2020年中央对地方转移支付分地区决算表`

Contains regional breakdowns:
```
地区 | 2020年预算数 | 2020年决算数
北京市 | 910.30 | 1054.74
天津市 | 515.10 | 612.88
河北省 | 3138.91 | 3938.11
...
```

## Functions

### `extract_table`

Extract financial data from a single table URL.

**Parameters:**
- `url` (string, required): URL of the financial table page

**Returns:**
```json
{
  "success": true,
  "url": "...",
  "title": "2020年中央对地方转移支付分地区决算表...",
  "year": "2020",
  "table_type": "by_region",
  "unit": "亿元",
  "headers": ["地区", "2020年预算数", "2020年决算数"],
  "total_rows": 46,
  "data": [
    {
      "region": "北京市",
      "is_breakdown": false,
      "2020年预算数": 910.3,
      "2020年决算数": 1054.74
    },
    ...
  ]
}
```

### `extract_tables`

Extract multiple tables in batch.

**Parameters:**
- `urls` (array, required): List of URLs

**Returns:**
```json
{
  "success": true,
  "total_urls": 2,
  "results": [...]
}
```

### `list_available_tables`

List known sample table URLs.

## Data Extraction Features

1. **Merged Cell Handling**: Properly processes HTML tables with `rowspan` and `colspan` attributes
2. **Numeric Parsing**: Converts Chinese/western numeric formats including percentages
3. **Hierarchy Detection**: Identifies category levels (一、, 二、, etc.)
4. **Metadata Extraction**: Captures year, unit (亿元), and table type
5. **Regional Sub-items**: Identifies sub-regions (e.g., 大连市 under 辽宁省)

## Sample URLs

| URL | Description |
|-----|-------------|
| `http://yss.mof.gov.cn/2020zyjs/202106/t20210629_3727251.htm` | 2020 Central to Local Transfer Payments by Region |
| `http://yss.mof.gov.cn/2021zyjs/202207/t20220712_3826596.htm` | 2021 Central to Local Transfer Payments Summary |
| `http://yss.mof.gov.cn/2021zyjs/202207/t20220712_3826588.htm` | 2021 General Transfer Payments by Region |

## Technical Notes

- Uses direct HTTP requests (no JavaScript required)
- Parses HTML with BeautifulSoup
- Handles Chinese whitespace and formatting
- No authentication required
- Rate limit: 2 requests/second recommended

## Error Handling

Returns structured errors:
```json
{
  "success": false,
  "error": "Failed to fetch page",
  "url": "..."
}
```