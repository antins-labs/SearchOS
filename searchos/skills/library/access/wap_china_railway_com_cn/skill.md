# China Railway National Indicators Data Access

## Overview

This skill fetches official statistical data from China Railway's (中国国家铁路集团有限公司) data service portal. The site provides monthly and cumulative statistics on national railway operations.

## Data Available

The skill extracts structured data from "国家铁路主要指标完成情况" (National Railway Main Indicators Completion Status) reports, which include:

### Railway Transport Indicators (铁路运输)
1. **旅客发送量** (Passenger Volume) - in 万人 (ten thousand passengers)
2. **旅客周转量** (Passenger Turnover) - in 亿人公里 (100 million passenger-km)
3. **货运总发送量** (Total Freight Volume) - in 万吨 (ten thousand tons)
4. **货运总周转量** (Total Freight Turnover) - in 亿吨公里 (100 million ton-km)
5. **总换算周转量** (Total Converted Turnover) - in 亿吨公里

### Investment
- **全国铁路固定资产投资** (National Railway Fixed Asset Investment) - in 亿元 (100 million yuan)

### Each indicator includes:
- Current period value (完成)
- Previous year same period (上年同期完成)
- Year-over-year change (比上年同期增减)
- Year-over-year percentage change (比上年同期增减%)

## Functions

### list_reports
Returns all available reports with their titles, URLs, years, and periods.

```python
result = await execute({'function': 'list_reports'})
# Returns: { success: True, total_reports: N, reports: [...] }
```

### get_report
Fetches a specific report by URL or title keyword.

```python
# By URL
result = await execute({
    'function': 'get_report',
    'url': 'http://wap.china-railway.com.cn/wnfw/sjfw/202602/t20260225_153132.html'
})

# By title keyword
result = await execute({
    'function': 'get_report',
    'title_keyword': '2026年1月'
})
```

### get_latest
Fetches the most recently published report.

```python
result = await execute({'function': 'get_latest'})
```

## Output Structure

Each report contains:

```json
{
  "success": true,
  "url": "...",
  "title": "2026年1月国家铁路主要指标完成情况",
  "year": 2026,
  "period": "1月",
  "period_type": "monthly",
  "indicators": {
    "transport": {
      "1.旅客发送量": {
        "unit": "万人",
        "value": "32149",
        "previous_year": "34484",
        "change": "-2336",
        "change_percent": "-6.8"
      },
      ...
    },
    "investment": { ... },
    "notes": ["注：统计范围不含港澳台..."]
  },
  "table_rows": [...]
}
```

## Period Types

- `monthly`: Single month reports (e.g., "1月")
- `cumulative`: Cumulative period reports (e.g., "1-5月")  
- `annual`: Full year reports ("全年")

## Notes

- Statistics exclude Hong Kong, Macau, and Taiwan (统计范围不含港澳台)
- Data is provided by China Railway Development and Reform Department (国铁集团发改部)
- Reports are typically published monthly, with titles indicating the reporting period

## Technical Details

- Data source: Static HTML pages with embedded tables
- No authentication required
- Mobile-friendly WAP site format
- Direct HTTP requests with aiohttp (no JavaScript rendering needed)