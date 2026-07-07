# China Ministry of Commerce Open Data Portal Access Skill

This skill provides access to [opendata.mofcom.gov.cn](https://opendata.mofcom.gov.cn), China's Ministry of Commerce open data portal.

## Overview

The portal hosts various datasets including:
- Enterprise rankings (e.g., Fortune Global 500 companies)
- Trade statistics
- Foreign investment data
- Policy documents and guidelines
- Import/export regulations

## Available Functions

### 1. `list_datasets`

Lists all available datasets from the portal.

**Example:**
```python
result = await execute({
    "function": "list_datasets"
})
```

**Returns:**
```json
{
  "success": true,
  "total_datasets": 131,
  "returned_count": 20,
  "datasets": [
    {
      "id": "WM006",
      "title": "世界500强企业",
      "url": "https://opendata.mofcom.gov.cn/front/data/detail?id=WM006"
    },
    ...
  ]
}
```

### 2. `get_dataset`

Gets detailed information about a specific dataset.

**Parameters:**
- `dataset_id` (required): The dataset ID (e.g., "WM006")

**Example:**
```python
result = await execute({
    "function": "get_dataset",
    "dataset_id": "WM006"
})
```

**Returns:**
```json
{
  "id": "WM006",
  "title": "世界500强企业",
  "abstract": "包括企业名称、排名、利润、营业收入等信息。",
  "metadata": {
    "更新频率": "年",
    "数据提供方": "外资司",
    "最后更新时间": "2026-02-05 15:29:57",
    "开放属性": "完全开放",
    "数据主题": "对外贸易",
    "数据类型": "名单名录",
    "数据格式": "HTML XLSX CSV"
  },
  "download_files": [
    {
      "name": "2025年世界500强名单_20260205_00013.xlsx",
      "id": "029E68185BD757E8375D838E6DAF01F4",
      "url": "https://opendata.mofcom.gov.cn/front/data/download?id=...",
      "requires_login": true
    },
    ...
  ]
}
```

### 3. `get_download_urls`

Gets download URLs for all files in a dataset.

**Parameters:**
- `dataset_id` (required): The dataset ID

**Example:**
```python
result = await execute({
    "function": "get_download_urls",
    "dataset_id": "WM006"
})
```

## Important Notes

### Login Requirement

**File downloads require user authentication.** The download URLs will only work with an authenticated session. To download files:

1. Log in at [user.mofcom.gov.cn/login](https://user.mofcom.gov.cn/login)
2. Visit the dataset detail page
3. Click the download button for the desired file

### SSL Compatibility

This skill uses Playwright for fetching because the site has SSL/TLS compatibility issues with standard Python HTTP clients (aiohttp, httpx, requests).

### Data Formats

Files are typically available in:
- XLSX (Excel)
- CSV
- PDF
- HTML

## Popular Datasets

| ID | Title | Description |
|----|-------|-------------|
| WM006 | 世界500强企业 | Fortune Global 500 list with rankings, revenue, profits |
| QT004 | 中国对外经济贸易文告库 | China foreign trade bulletin repository |
| BC88824FFB8D4C862826F5513E099446 | 社会融资规模增量统计 | Social financing scale statistics |

## Limitations

1. **No direct downloads**: Files cannot be downloaded directly via the skill due to login requirements
2. **Rate limiting**: Be respectful of the server when making multiple requests
3. **Chinese language**: Most dataset titles and metadata are in Chinese

## Use Cases

1. **Data Discovery**: List all available datasets to find relevant data
2. **Metadata Extraction**: Get detailed information about datasets including update frequency, provider, and available formats
3. **URL Retrieval**: Get download URLs for manual download after logging in
4. **Research**: Understand what enterprise ranking data is available from China's Ministry of Commerce