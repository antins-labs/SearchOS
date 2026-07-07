# NRA Railway Statistics Access Skill

Access skill for the China National Railway Administration (国家铁路局) railway statistics portal.

## Website

**URL:** http://www.nra.gov.cn/xwzx/zlzx/hytj/

This portal publishes monthly railway statistics including:
- Passenger volume and turnover
- Freight volume and turnover  
- Fixed asset investment
- Other railway performance indicators

## Key Challenges

### 1. Dual Content Formats

The website uses two different formats for publishing data:

**HTML Tables (older articles, typically 2024 and earlier):**
- Data is embedded in HTML `<table>` elements
- Tables have standardized structure with columns:
  - 指标 (Indicator)
  - 计算单位 (Unit)
  - 本月 (Current Month)
  - 比上年同期增长% (YoY Growth %)
  - 当年累计 (Year-to-date)
  - 比上年同期增长% (YoY Growth %)

**JPEG Images (newer articles, typically 2025 onwards):**
- Data is presented as an embedded image (`<img>` tag)
- No accessible text data in the HTML
- Images require download and separate OCR processing

### 2. Chinese Government Website Patterns

- URLs use specific patterns:
  - List pages: `/xwzx/zlzx/hytj/` or `/xwzx/zlzx/hytj/index_{n}.shtml`
  - Article pages: `/xwzx/zlzx/hytj/YYYYMM/tYYYYMMDD_ID.shtml`
- Encoding may be GB2312, GBK, or UTF-8
- Content is in `#zoom` div element
- Metadata in structured info blocks

### 3. Pagination

- Uses 0-indexed pagination: `index_1.shtml` = page 2
- Page 1 is the base URL or `index.shtml`
- Total page count embedded in JavaScript

## Functions

### list_articles

List articles from the railway statistics portal.

```python
result = await execute({
    'function': 'list_articles',
    'page': 1  # optional, default 1
})
```

**Returns:**
```json
{
  "articles": [
    {
      "title": "2026年4月份全国铁路主要指标完成情况",
      "url": "http://www.nra.gov.cn/xwzx/zlzx/hytj/202605/t20260512_351217.shtml",
      "article_id": "351217",
      "date": "2026-05-12"
    }
  ],
  "total_pages": 21,
  "current_page": 1,
  "count": 8
}
```

### get_article

Get article details and extract statistical table data.

```python
result = await execute({
    'function': 'get_article',
    'url': 'http://www.nra.gov.cn/xwzx/zlzx/hytj/202204/t20220405_338094.shtml'
})
```

**Returns (for HTML table articles):**
```json
{
  "metadata": {
    "title": "2020年12月份全国铁路主要指标完成情况",
    "has_image_table": false
  },
  "tables": [
    {
      "headers": ["指标", "计算单位", "本月", "比上年同期增长%", "当年累计", "比上年同期增长%"],
      "rows": [
        {
          "指标": "1.旅客发送量",
          "计算单位": "万人",
          "本月": "20768",
          "比上年同期增长%": "-21.1",
          "当年累计": "220349"
        }
      ]
    }
  ],
  "has_data": true,
  "has_image_table": false
}
```

**Returns (for image-based articles):**
```json
{
  "metadata": {
    "title": "2026年4月份全国铁路主要指标完成情况",
    "has_image_table": true
  },
  "tables": [],
  "has_data": false,
  "has_image_table": true,
  "image_url": "http://www.nra.gov.cn/xwzx/zlzx/hytj/202605/W020260512646560621585.jpg"
}
```

### get_article_image

Download the table image for image-based articles.

```python
result = await execute({
    'function': 'get_article_image',
    'url': 'http://www.nra.gov.cn/xwzx/zlzx/hytj/202605/t20260512_351217.shtml'
})
```

**Returns:**
```json
{
  "url": "http://www.nra.gov.cn/xwzx/zlzx/hytj/202605/t20260512_351217.shtml",
  "image_url": "http://www.nra.gov.cn/xwzx/zlzx/hytj/202605/W020260512646560621585.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 45678,
  "data": "<base64-encoded-image-data>"
}
```

### get_stats_history

Aggregate statistics from multiple articles across pages.

```python
result = await execute({
    'function': 'get_stats_history',
    'start_page': 1,
    'end_page': 3,
    'max_articles': 10
})
```

## Usage Examples

### Get Latest Month's Statistics

```python
# 1. List recent articles
articles = await execute({'function': 'list_articles', 'page': 1})

# 2. Get the most recent article
latest = articles['articles'][0]
article = await execute({'function': 'get_article', 'url': latest['url']})

# 3. Check if it's image-based
if article['has_image_table']:
    # Download image for OCR
    img = await execute({'function': 'get_article_image', 'url': latest['url']})
    # Process img['data'] with OCR
else:
    # Use extracted table data
    table_data = article['tables'][0]
```

### Historical Data Collection

```python
# Get data from multiple articles
history = await execute({
    'function': 'get_stats_history',
    'start_page': 1,
    'end_page': 5,
    'max_articles': 50
})

# Filter for HTML-table articles with extractable data
extractable = [a for a in history['articles'] if a['has_data']]
image_based = [a for a in history['articles'] if a['has_image_table']]
```

## Data Structure

The extracted table data follows the official NRA format:

| 指标 (Indicator) | 计算单位 (Unit) | 本月 (Current Month) | 比上年同期增长% (YoY %) | 当年累计 (YTD) | 比上年同期增长% (YoY %) |
|-----------------|----------------|---------------------|------------------------|----------------|------------------------|
| 一、铁路运输 | | | | | |
| 1.旅客发送量 | 万人 | 20768 | -21.1 | 220349 | -39.8 |
| 2.旅客周转量 | 亿人公里 | 700.83 | -24.1 | 8266.19 | -43.8 |
| 3.货运总发送量 | 万吨 | 41600 | 4.0 | 455236 | 3.2 |
| 4.货运总周转量 | 亿吨公里 | 2832.86 | 2.5 | 30514.46 | 1.0 |
| 二、铁路固定资产投资累计完成额 | 亿元 | — | — | 7819 | -2.6 |

## Error Handling

All functions return structured error responses instead of raising exceptions:

```json
{
  "error": "HTTP 404: http://...",
  "articles": [],
  "page": 1
}
```

Common errors:
- Invalid URL format
- Non-existent page number
- Network timeout
- Content encoding issues

## Rate Limiting

To avoid overwhelming the server:
- Use `get_stats_history` which includes built-in delays
- Limit concurrent requests
- Consider caching results for repeated access