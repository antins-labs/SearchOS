# Forbes China Lists Access Skill

This skill extracts wealth ranking and leaderboard data from Forbes China (www.forbeschina.com), including billionaire rankings and other financial lists.

## Overview

Forbes China hosts various wealth ranking lists on their website. Unlike many modern sites that load data via AJAX/API calls, Forbes China renders complete table data server-side in HTML, making extraction fast and reliable without needing to handle dynamic API requests or pagination.

### Supported Lists

Known list URLs include:
- `https://www.forbeschina.com/lists/1828` - 2024 Global Billionaires (全球亿万富豪榜)
- `https://www.forbeschina.com/lists/1757` - 2021 Global Billionaires (全球富豪榜)
- And many other Forbes China ranking lists

## Functions

### get_list

Retrieve complete list data with optional pagination.

**Parameters:**
- `url` (string, required): Forbes China list URL or list ID (e.g., `1828` or full URL)
- `limit` (integer, optional): Maximum number of records to return
- `offset` (integer, optional): Number of records to skip (default: 0)

**Returns:**
```json
{
  "success": true,
  "url": "https://www.forbeschina.com/lists/1828",
  "list_id": "1828",
  "metadata": {
    "page_title": "2024福布斯 - 全球亿万富豪榜 - ...",
    "year": "2024福布斯",
    "list_title": "全球亿万富豪榜",
    "total_records": 2781,
    "returned_records": 10,
    "offset": 0,
    "limit": 10
  },
  "headers": ["排名", "姓名（英文）", "姓名（中文）", "财富值（亿美元）", "财富来源", "国家和地区"],
  "records": [
    {
      "rank": 1,
      "name_en": "Bernard Arnault & family",
      "name_cn": "伯纳德·阿尔诺及家族",
      "wealth_billion_usd": 2330.0,
      "wealth_source": "LVMH",
      "country_region": "法国"
    },
    ...
  ]
}
```

### search_records

Search and filter list records by various criteria.

**Parameters:**
- `url` (string, required): Forbes China list URL or list ID
- `query` (string, optional): Search query for name matching (searches English name, Chinese name, and wealth source)
- `country` (string, optional): Filter by country/region (partial match)
- `min_rank` (integer, optional): Minimum rank (inclusive)
- `max_rank` (integer, optional): Maximum rank (inclusive)
- `min_wealth` (number, optional): Minimum wealth in billions USD
- `max_wealth` (number, optional): Maximum wealth in billions USD
- `limit` (integer, optional): Maximum number of results to return

**Returns:**
```json
{
  "success": true,
  "url": "https://www.forbeschina.com/lists/1828",
  "list_id": "1828",
  "metadata": {
    "year": "2024福布斯",
    "list_title": "全球亿万富豪榜",
    "total_records": 2781,
    "filtered_records": 15,
    "query": "Musk",
    "filters": {
      "country": null,
      "min_rank": null,
      "max_rank": null,
      "min_wealth": null,
      "max_wealth": null
    }
  },
  "records": [
    {
      "rank": 2,
      "name_en": "Elon Musk",
      "name_cn": "埃隆·马斯克",
      "wealth_billion_usd": 1950.0,
      "wealth_source": "特斯拉、SpaceX",
      "country_region": "美国"
    }
  ]
}
```

## Standardized Fields

The skill automatically standardizes Chinese field names to English:

| Chinese | English | Type |
|---------|---------|------|
| 排名 | rank | integer |
| 姓名（英文） | name_en | string |
| 姓名（中文） | name_cn | string |
| 财富值（亿美元）/ 财富（亿美元） | wealth_billion_usd | float |
| 财富来源 | wealth_source | string |
| 国家和地区 | country_region | string |
| 年龄 | age | integer |

## Usage Examples

### Get top 10 billionaires from 2024 list

```python
result = await execute({
    'function': 'get_list',
    'url': 'https://www.forbeschina.com/lists/1828',
    'limit': 10
})
```

### Search for billionaires from China

```python
result = await execute({
    'function': 'search_records',
    'url': 'https://www.forbeschina.com/lists/1828',
    'country': '中国内地',
    'limit': 20
})
```

### Find billionaires with wealth between 50-100 billion

```python
result = await execute({
    'function': 'search_records',
    'url': 'https://www.forbeschina.com/lists/1828',
    'min_wealth': 50,
    'max_wealth': 100
})
```

### Search by name

```python
result = await execute({
    'function': 'search_records',
    'url': 'https://www.forbeschina.com/lists/1828',
    'query': 'Musk'
})
```

### Get billionaires ranked 100-200

```python
result = await execute({
    'function': 'search_records',
    'url': 'https://www.forbeschina.com/lists/1828',
    'min_rank': 100,
    'max_rank': 200
})
```

### Use list ID instead of full URL

```python
# These are equivalent:
result = await execute({'function': 'get_list', 'url': '1828'})
result = await execute({'function': 'get_list', 'url': 'https://www.forbeschina.com/lists/1828'})
```

## Implementation Details

### Data Source

- **Method**: Direct HTML extraction (no API calls)
- **Table ID**: `data-view`
- **Data Format**: Server-side rendered HTML table with complete dataset
- **Pagination**: Not required - all data available in single page load (typically 2700+ records)

### Technical Notes

1. **SSL Certificate**: The site uses SSL certificates that may trigger warnings in some contexts. The skill disables SSL verification to handle this.

2. **Data Completeness**: Unlike many modern sites that use lazy-loading or pagination APIs, Forbes China delivers all records in the initial HTML response, making extraction straightforward.

3. **Character Encoding**: The site uses UTF-8 encoding. Chinese characters are preserved as-is.

4. **Rate Limiting**: Standard HTTP client with reasonable timeouts. No aggressive scraping needed since data is delivered in one request.

### Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "HTTP 404: Failed to fetch page",
  "url": "https://www.forbeschina.com/lists/9999"
}
```

Common errors:
- Invalid list ID or URL
- Network timeout
- Missing table element
- Invalid parameters

## Testing

Run the built-in tests:

```python
import asyncio
from executor import test_extraction

asyncio.run(test_extraction())
```

This will test extraction from known URLs and verify data structure.