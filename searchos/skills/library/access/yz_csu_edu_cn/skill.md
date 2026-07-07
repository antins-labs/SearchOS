# CSU Graduate Admissions Portal Access Skill

**Host:** yz.csu.edu.cn  
**Institution:** 中南大学 (Central South University)  
**Category:** Graduate Admissions

## Overview

This skill provides structured access to the Central South University Graduate Admissions Portal. It retrieves admission notices, score requirement tables, publicity lists, and other recruitment information without requiring browser automation.

## Features

- **List Categories**: Browse all available article categories
- **Paginated Lists**: Navigate through article listings with pagination
- **Article Extraction**: Fetch full article content with structured data
- **Table Parsing**: Extract score requirement tables as structured JSON
- **Search**: Find articles by keyword across categories
- **Attachments**: Extract links to downloadable files

## Available Functions

### 1. `list_categories`

List all available article categories.

**Parameters:** None

**Example:**
```json
{
  "function": "list_categories"
}
```

**Returns:**
```json
{
  "success": true,
  "categories": [
    {"key": "master_notices", "name": "硕士招生通知公告", "list_url": "https://yz.csu.edu.cn/sszs/tzgg.htm"},
    {"key": "doctor_notices", "name": "博士招生通知公告", "list_url": "https://yz.csu.edu.cn/bszs/tzgg.htm"},
    ...
  ]
}
```

### 2. `list_articles`

List articles in a specific category with pagination.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| category | string | No | Category key (default: master_notices) |
| page | integer | No | Page number (default: 1) |

**Example:**
```json
{
  "function": "list_articles",
  "category": "master_notices",
  "page": 1
}
```

**Returns:**
```json
{
  "success": true,
  "category": "master_notices",
  "category_name": "硕士招生通知公告",
  "page": 1,
  "pagination": {
    "current_page": 1,
    "total_pages": 9,
    "has_next": true,
    "has_prev": false
  },
  "articles": [
    {
      "title": "关于发放2026级硕士研究生录取通知书的通知",
      "url": "https://yz.csu.edu.cn/info/1009/1518.htm",
      "article_id": "1518",
      "date": "2026-06-18"
    },
    ...
  ]
}
```

### 3. `get_article`

Fetch a single article with full content and parsed tables.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| url | string | Yes | Article URL or relative path |

**Example:**
```json
{
  "function": "get_article",
  "url": "https://yz.csu.edu.cn/info/1009/1391.htm"
}
```

**Returns:**
```json
{
  "success": true,
  "url": "https://yz.csu.edu.cn/info/1009/1391.htm",
  "article_id": "1391",
  "title": "中南大学2025年全国硕士研究生招生考试考生进入复试的初试成绩基本要求",
  "date": "2025年3月",
  "content": "经学校研究生招生工作领导小组审议批准...",
  "tables": [
    [
      {"学科门类": "哲学[01]", "一级学科、专业学位类别": "各学科专业", "总分": "330", ...},
      {"学科门类": "经济学[02]", "一级学科、专业学位类别": "各学科专业", "总分": "365", ...},
      ...
    ]
  ],
  "attachments": []
}
```

### 4. `search`

Search for articles by keyword.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| query | string | Yes | Search keyword |
| category | string | No | Optional category to search within |
| max_pages | integer | No | Max pages per category (default: 3) |

**Example:**
```json
{
  "function": "search",
  "query": "复试"
}
```

## Categories

| Key | Name (Chinese) | English Description |
|-----|----------------|---------------------|
| master_notices | 硕士招生通知公告 | Master's admission notices |
| doctor_notices | 博士招生通知公告 | Doctoral admission notices |
| master_publicity | 硕士招生公示 | Master's admission publicity lists |
| doctor_publicity | 博士招生公示 | Doctoral admission publicity lists |
| gatzs_notices | 港澳台招生通知公告 | HK/Macau/Taiwan admissions |
| downloads | 下载专区 | Download area |
| master_brochure | 硕士招生简章 | Master's admission brochures |
| doctor_brochure | 博士招生简章 | Doctoral admission brochures |

## Use Cases

### 1. Get Latest Admission Score Requirements
```json
{
  "function": "list_articles",
  "category": "master_notices",
  "page": 1
}
```
Then fetch articles containing "初试成绩基本要求" (score requirements).

### 2. Extract Score Tables
Articles containing admission score requirements have structured tables with columns like:
- 学科门类 (Discipline Category)
- 一级学科、专业学位类别 (Primary Disciplines)
- 总分 (Total Score)
- 单科 (Subject Score thresholds)
- 备注 (Notes)

### 3. Find Admission Notices by Year
```json
{
  "function": "search",
  "query": "2025",
  "category": "master_notices"
}
```

### 4. Get Publicity Lists (Admitted Students)
```json
{
  "function": "list_articles",
  "category": "master_publicity"
}
```

## Technical Notes

- **HTTP Direct Access**: No browser automation needed; direct HTTP requests work reliably
- **No Authentication**: All public content accessible without login
- **Rate Limiting**: Built-in rate limiting to respect server resources
- **Chinese Language**: All content is in Chinese; search terms should be in Chinese for best results
- **Character Encoding**: UTF-8
- **Pagination**: Uses numeric page structure (`/path/N.htm`)

## Example Workflows

### Extract Score Requirements for All Disciplines
1. List articles in "master_notices"
2. Find article with "初试成绩基本要求" in title
3. Get article content
4. Parse tables array for structured score data

### Monitor New Admission Notices
1. Call `list_articles` with `page: 1`
2. Compare article IDs with last check
3. Fetch new articles that haven't been seen