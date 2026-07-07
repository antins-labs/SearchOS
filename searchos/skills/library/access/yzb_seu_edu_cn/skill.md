# Southeast University Graduate Admission Scores Access Skill

This skill provides programmatic access to Southeast University (东南大学) graduate admission score data from the Graduate Admissions Office website (yzb.seu.edu.cn).

## Overview

The Southeast University Graduate Admissions Office publishes two main types of score data:

1. **Department-Specific Scores (复试分数线)**: Detailed admission cut-offs for each department, major, and research direction
2. **Basic Scores (复试基本线)**: University-wide minimum score requirements by academic discipline

## Available Functions

### get_department_scores

Fetches department-specific admission score cut-offs including scores for each subject and total.

**Parameters:**
- `url` (required): URL of the department scores page

**Example:**
```python
result = await execute({
    'function': 'get_department_scores',
    'url': 'https://yzb.seu.edu.cn/2025/0905/c6674a538419/page.htm'
})
```

**Output Structure:**
```json
{
  "success": true,
  "url": "https://yzb.seu.edu.cn/2025/0905/c6674a538419/page.htm",
  "title": "2025年东南大学各院系所复试分数线",
  "publish_date": "2025-09-05",
  "headers": ["院系", "专业代码", "专业名称", "研究方向码", "研究方向名称", "政治", "英语", "业务课一", "业务课二", "总分"],
  "data": [
    {
      "院系": "001 建筑学院",
      "专业代码": "081300",
      "专业名称": "建筑学",
      "研究方向码": "01,02,03",
      "研究方向名称": "建筑设计及其理论,城市设计与理论,建筑历史与理论及遗产保护",
      "政治": "50",
      "英语": "50",
      "业务课一": "90",
      "业务课二": "90",
      "总分": "345"
    }
  ],
  "row_count": 174
}
```

### get_basic_scores

Fetches university-wide basic score requirements, typically published as PDF documents.

**Parameters:**
- `url` (required): URL of the basic scores page

**Example:**
```python
result = await execute({
    'function': 'get_basic_scores',
    'url': 'https://yzb.seu.edu.cn/2025/0314/c6676a521705/page.htm'
})
```

**Output Structure:**
```json
{
  "success": true,
  "url": "https://yzb.seu.edu.cn/2025/0314/c6676a521705/page.htm",
  "pdf_url": "https://yzb.seu.edu.cn/_upload/article/files/.../filename.pdf",
  "type": "pdf",
  "text": "东南大学 2025年硕士研究生复试基本线..."
}
```

### get_page

Generic page fetcher that auto-detects content type (HTML table or PDF).

**Parameters:**
- `url` (required): Any page URL from yzb.seu.edu.cn
- `timeout` (optional): Request timeout in seconds (default: 30)

### list_known_pages

Returns a list of known score page URLs for reference.

**Example:**
```python
result = await execute({'function': 'list_known_pages'})
```

## Data Fields Explained

### Department Scores Table

| Field | Description | Example |
|-------|-------------|---------|
| 院系 | Department name with numeric code | 001 建筑学院 |
| 专业代码 | 6-digit major code | 081300 |
| 专业名称 | Major name | 建筑学 |
| 研究方向码 | Research direction code(s) | 01,02,03 or -- |
| 研究方向名称 | Research direction name(s) | 建筑设计及其理论,... or 不区分研究方向 |
| 政治 | Minimum politics score | 50 |
| 英语 | Minimum English score | 50 |
| 业务课一 | Minimum professional course 1 score | 90 |
| 业务课二 | Minimum professional course 2 score | 90 |
| 总分 | Minimum total score | 345 |

### Basic Scores (PDF Content)

The basic scores PDF contains:
- Academic degree (学术学位) requirements by discipline category
- Professional degree (专业学位) requirements by field
- Special programs (其他) including:
  - Southeast University-Monash University Joint Graduate School
  - Rennes Graduate School
  - Special programs for retired military students, ethnic minority students, etc.

## Implementation Details

### Data Extraction

1. **HTML Tables**: Department scores are embedded in HTML tables within `.Article_Content` div. The skill uses BeautifulSoup to parse the table structure and extract structured data.

2. **PDF Documents**: Basic scores are typically published as PDF files embedded via iframe. The skill:
   - Detects PDF URLs from iframe elements
   - Downloads PDF with proper headers (Referer required)
   - Extracts text using PyPDF2

### URL Pattern

URLs follow the pattern:
```
https://yzb.seu.edu.cn/{YEAR}/{MONTH_DAY}/c{CATEGORY}a{ID}/page.htm
```

For example:
- `2025/0905/c6674a538419/page.htm` - Year 2025, September 5
- `2025/0314/c6676a521705/page.htm` - Year 2025, March 14

### Headers Required

PDF downloads require proper headers:
```
User-Agent: Mozilla/5.0 ...
Referer: https://yzb.seu.edu.cn/{original_page_url}
Accept: application/pdf,*/*
```

Without the Referer header, PDF downloads return 403 Forbidden.

## Error Handling

The skill returns structured error responses instead of raising exceptions:

```json
{
  "success": false,
  "error": "Failed to fetch page: HTTP 404",
  "url": "https://..."
}
```

Common errors:
- `HTTP 403`: Missing required headers (usually for PDF downloads)
- `HTTP 404`: Page not found
- `Missing required parameter`: Missing function or URL parameter
- `No score table found`: Page exists but doesn't contain expected data structure

## Dependencies

- `aiohttp`: Async HTTP client
- `beautifulsoup4`: HTML parsing
- `PyPDF2`: PDF text extraction

## Known Pages

As of 2025:
- Department Scores: `https://yzb.seu.edu.cn/2025/0905/c6674a538419/page.htm`
- Basic Scores: `https://yzb.seu.edu.cn/2025/0314/c6676a521705/page.htm`

New pages are typically published each year around March-April (basic scores) and September (department scores).

## Notes

1. **Hidden Content**: The notes mention "hidden iframes" - this refers to the PDF viewer iframe used for basic scores. The skill handles this by detecting and downloading the PDF directly.

2. **Score Updates**: Scores may be updated throughout the admission season. Always check the publish date and refresh cached data as needed.

3. **Score Interpretation**: 
   - "--" for research direction means "不区分研究方向" (no specific research direction)
   - "0" in subject scores may indicate that subject is not applicable (e.g., for professional degrees with fewer exam subjects)
   - Total scores are minimum requirements; individual departments may set higher requirements