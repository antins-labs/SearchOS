# HymExpo Beijing Exhibition Schedule

This skill fetches and parses Beijing exhibition schedule data from www.hymexpo.com (恒毅铭展览展示有限公司), specifically from their 2025 Beijing exhibition schedule page.

## Overview

The skill extracts structured exhibition schedule data including:
- Exhibition names
- Exhibition dates
- Exhibition venues
- Month groupings

## Available Functions

### 1. `get_schedule`

Fetches the complete Beijing exhibition schedule for 2025.

**Parameters:**
- `function`: "get_schedule"
- `url` (optional): Custom URL to fetch from

**Example:**
```python
result = await execute({
    'function': 'get_schedule'
})
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.hymexpo.com/sys-nd/185.html",
  "exhibitions": [
    {
      "month": "1月展会",
      "name": "2025第37届北京图书订货会",
      "date": "1/9~1/11",
      "venue": "中国国际展览中心（朝阳馆）"
    },
    ...
  ],
  "month_groups": {
    "1月展会": [...],
    "2月展会": [...],
    ...
  },
  "total_count": 150
}
```

### 2. `search`

Searches for exhibitions matching a keyword in their name or venue.

**Parameters:**
- `function`: "search"
- `keyword`: Search term (required)
- `url` (optional): Custom URL to fetch from

**Example:**
```python
result = await execute({
    'function': 'search',
    'keyword': '汽车'
})
```

**Returns:**
```json
{
  "success": true,
  "keyword": "汽车",
  "url": "https://www.hymexpo.com/sys-nd/185.html",
  "exhibitions": [
    {
      "month": "2月展会",
      "name": "第36届中国国际汽车服务用品及设备展览会暨中国国际新能源汽车技术、零部件及服务展览会",
      "date": "2/21~2/24",
      "venue": "中国国际展览中心(顺义馆）"
    },
    ...
  ],
  "total_count": 5
}
```

### 3. `get_by_month`

Gets exhibitions for a specific month (1-12).

**Parameters:**
- `function`: "get_by_month"
- `month`: Month number 1-12 (required)
- `url` (optional): Custom URL to fetch from

**Example:**
```python
result = await execute({
    'function': 'get_by_month',
    'month': 3
})
```

**Returns:**
```json
{
  "success": true,
  "month": 3,
  "month_name": "3月展会",
  "url": "https://www.hymexpo.com/sys-nd/185.html",
  "exhibitions": [
    {
      "month": "3月展会",
      "name": "2025北京国际家居产业博览会",
      "date": "3/6~3/9",
      "venue": "中国国际展览中心(顺义馆）"
    },
    ...
  ],
  "total_count": 23
}
```

## Data Source

The data is scraped from the Beijing exhibition company "北京恒毅铭展览展示有限公司" website:
- Default URL: https://www.hymexpo.com/sys-nd/185.html
- Content: 2025 Beijing Exhibition Schedule (2025北京展会排期计划)

## Notes

- The schedule includes exhibitions from January to December 2025
- Each exhibition entry includes the exhibition name, date range, and venue
- Venues include major Beijing exhibition centers like:
  - 中国国际展览中心（朝阳馆）
  - 中国国际展览中心(顺义馆）
  - 北京国家会议中心
  - 北京国际会议中心
  - 全国农业展览馆
  - 北京展览馆
  - 北京首钢会展中心

## Error Handling

All functions return a consistent structure with:
- `success`: Boolean indicating if the operation succeeded
- `error`: Error message (only present if success is false)
- Other fields relevant to the specific function

Example error response:
```json
{
  "success": false,
  "error": "Missing required parameter 'keyword' for search function"
}
```