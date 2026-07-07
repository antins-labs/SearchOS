# BJEEA (Beijing Education Examination Authority) Access Skill

## Overview

This skill provides programmatic access to the Beijing Education Examination Authority website (www.bjeea.cn), the official source for college admission data in Beijing, China. The website hosts critical structured data including admission score tables, score distribution statistics, and examination announcements.

## Why This Skill Was Needed

Prior to this skill, the generic reader failed to extract data from this website (112 attempts with zero evidence extracted). This was due to:

1. **Large HTML pages**: Some pages exceed 6MB with embedded tables containing 1000+ rows
2. **Complex table structures**: Tables with merged cells and mixed content types
3. **Chinese-first design**: The site is primarily in Chinese with specific encoding requirements
4. **Dynamic content markers**: While content is server-rendered, proper parsing requires understanding the HTML structure

## Key Features

### 1. **Data Table Extraction**
Extracts complete admission score tables with proper column headers:
- 序号 (Number)
- 院校 (University code/name)
- 专业组 (Major group)
- 总分 (Total score)
- 语文/数学/外语 (Chinese/Math/English scores)
- 三科选考 (Elective subjects)
- 其他要求 (Other requirements)

Example: The 2024 undergraduate admission score table contains 1,259 rows of university admission data.

### 2. **Document Link Discovery**
Automatically identifies and classifies document links:
- PDF files (score distribution statistics)
- HTML pages (detailed announcements)
- Filters by relevance (admission, scores, statistics keywords)

### 3. **Structured Metadata**
Extracts key metadata:
- Article title from `.info-ctit` element
- Publication date from `.info-item` element
- Content type classification (data_page, index_page, mixed_page)

## Available Functions

### `fetch_announcement`

Fetch and parse a specific announcement page.

**Parameters:**
- `url` (required): URL of the announcement page
- `max_rows` (optional): Limit number of table rows returned (useful for large tables)

**Returns:**
```json
{
  "success": true,
  "url": "https://www.bjeea.cn/html/gkgz/tzgg/2024/0720/85632.html",
  "title": "北京市2024年高招本科普通批录取投档线",
  "date": "2024-07-20",
  "type": "data_page",
  "tables": [
    {
      "headers": ["序号", "院校", "专业组", "总分", "语文", "数学", "外语", "三科选考", "其他要求"],
      "rows": [
        ["1", "0321", "陆军工程大学", "01", "物理", "510", "99", "98", "112", "201", ""],
        ...
      ],
      "row_count": 1259
    }
  ],
  "summary": {
    "title": "北京市2024年高招本科普通批录取投档线",
    "date": "2024-07-20",
    "type": "data_page",
    "tables": 1,
    "total_rows": 1259
  }
}
```

### `search_announcements`

Search for announcements by category and year.

**Parameters:**
- `category` (optional): Category code (default: `gkgz` for 高考高招)
  - `gkgz`: College entrance exam and admissions (高考高招)
  - `zkzz`: High school entrance exam (中考中招)
- `year` (optional): Filter by year (e.g., 2024, 2023)

**Returns:**
```json
{
  "success": true,
  "links": [
    {
      "text": "2024年全国普通高等学校在京招生录取分数分布统计(本科批次)",
      "url": "https://www.bjeea.cn/uploads/20250613/202506131926-1.pdf",
      "type": "pdf"
    },
    {
      "text": "2024年北京市高考考生分数分布",
      "url": "https://www.bjeea.cn/html/gkgz/tzgg/2024/0624/85430.html",
      "type": "html"
    }
  ],
  "summary": {
    "category": "gkgz",
    "year": 2024,
    "link_count": 6
  }
}
```

## Usage Examples

### 1. Fetch Admission Score Data

```python
# Get complete 2024 admission scores (all rows)
result = await execute({
    "function": "fetch_announcement",
    "url": "https://www.bjeea.cn/html/gkgz/tzgg/2024/0720/85632.html"
})

# Get first 10 rows for quick preview
result = await execute({
    "function": "fetch_announcement",
    "url": "https://www.bjeea.cn/html/gkgz/tzgg/2024/0720/85632.html",
    "max_rows": 10
})
```

### 2. Find Statistics Documents

```python
# Get 2024 statistics index page
result = await execute({
    "function": "fetch_announcement",
    "url": "https://www.bjeea.cn/html/gkgz/tzgg/2025/0613/87140.html"
})

# Extract PDF links
pdfs = [link for link in result["links"] if link["type"] == "pdf"]
```

### 3. Search by Year

```python
# Find 2023 admission announcements
result = await execute({
    "function": "search_announcements",
    "category": "gkgz",
    "year": 2023
})
```

## Data Categories

The website organizes information into several categories:

1. **高考高招 (College Entrance & Admissions)** - `/html/gkgz/`
   - Undergraduate admission scores (本科普通批录取投档线)
   - Early admission scores (本科提前批录取投档线)
   - Score distribution statistics (分数分布统计)
   
2. **中考中招 (High School Entrance)** - `/html/zkzz/`
   - High school admission information
   
3. **研考研招 (Graduate Admissions)** - `/html/ykyz/`
   - Graduate school admission data

## Important URLs

### 2024 Admission Data
- Undergraduate admission scores: `https://www.bjeea.cn/html/gkgz/tzgg/2024/0720/85632.html`
- Statistics index: `https://www.bjeea.cn/html/gkgz/tzgg/2025/0613/87140.html`
- PDF: Score distribution (undergraduate): `https://www.bjeea.cn/uploads/20250613/202506131926-1.pdf`

### 2023 Admission Data
- Statistics index: `https://www.bjeea.cn/html/gkgz/tzgg/2024/0618/85376.html`
- Undergraduate admission scores: `https://www.bjeea.cn/html/gkgz/tzgg/2023/0717/84120.html`

## Technical Notes

### Response Sizes
- Data pages with large tables can be 6-7MB uncompressed
- The skill properly handles these large responses
- Use `max_rows` parameter to limit table size for previews

### Encoding
- Website uses UTF-8 encoding
- Chinese characters are properly preserved
-Whitespace normalization applied to table cells

### Rate Limiting
- No explicit rate limiting detected, but:
- Use reasonable request intervals when fetching multiple pages
- Large pages may take 2-5 seconds to fetch and parse

### Table Structure
- Tables are embedded directly in HTML (no JavaScript rendering)
- Some tables have non-standard structures with merged cells
- Empty cells are preserved as empty strings

## Error Handling

The skill returns structured error responses:

```json
{
  "error": "timeout",
  "message": "Request timed out after 60.0s"
}
```

```json
{
  "error": "http_error",
  "message": "HTTP 404",
  "status_code": 404
}
```

## Limitations

1. **PDF Content**: This skill identifies PDF links but does not download or parse PDF content
2. **Historical Data**: Some older URLs may no longer be accessible
3. **Table Complexity**: Very complex table structures may not parse perfectly (uncommon)
4. **Language**: Content is primarily in Chinese; no translation provided

## Data Freshness

- Admission scores are published annually (typically July-August)
- Score distributions are published around June-July
- Update frequency varies by data type

## Source

Official website: https://www.bjeea.cn/

This is an official government website (Beijing Education Examination Authority) providing authoritative admission data for Beijing, China.