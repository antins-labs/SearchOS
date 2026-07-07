# Graduate Admission Score Lines (研究生招生分数线)

## Overview

This skill provides programmatic access to the Chinese graduate admission score line data from yz.chsi.com.cn, the official China Graduate Admission Information Network (研招网). The site is maintained by the Ministry of Education and is the authoritative source for:

- **34 Self-determined Score Line Universities** (34所自主划线院校): Elite universities authorized to set independent admission thresholds
- **National Minimum Score Lines** (国家线): Ministry of Education baseline thresholds
- **Provincial School Directories**: Complete lists of institutions by province

## Data Structure

### 34 Self-Determined Universities

These universities can independently set their复试 (re-examination) score thresholds:

```json
{
  "university": "北京大学",
  "years": [
    {"year": "2025", "url": "https://yz.chsi.com.cn/kyzx/fsfsx34/202503/..."},
    {"year": "2024", "url": "https://yz.chsi.com.cn/kyzx/fsfsx34/202403/..."},
    ...
  ]
}
```

### National Lines

Historical minimum score thresholds set annually:

```json
{
  "year": "2025",
  "url": "https://yz.chsi.com.cn/kyzx/kydt/202502/..."
}
```

### Province Search

Schools organized by province with query information:

```json
{
  "code": "10001",
  "name": "北京大学",
  "province": "北京",
  "query_method": "此站查询",
  "login_required": true
}
```

## Available Functions

### 1. list_34_universities

Get the list of 34 self-determined score line universities.

**Parameters:**
- `function`: "list_34_universities" (required)
- `university`: Filter by name (optional, partial match)
- `year`: Filter by year (optional)

**Example:**
```python
result = await execute({
    "function": "list_34_universities",
    "university": "北京",
    "year": "2025"
})
```

### 2. list_national_lines

Get national minimum score line URLs by year.

**Parameters:**
- `function`: "list_national_lines" (required)
- `year`: Filter by year (optional)

**Example:**
```python
result = await execute({
    "function": "list_national_lines"
})
```

### 3. list_provinces

Get all provinces with their codes for school lookup.

**Parameters:**
- `function`: "list_provinces" (required)

**Example:**
```python
result = await execute({
    "function": "list_provinces"
})
```

### 4. get_schools_by_province

Get schools in a specific province.

**Parameters:**
- `function`: "get_schools_by_province" (required)
- `province_code`: Province code like "11" (optional)
- `province_name`: Province name like "北京" (optional)

**Example:**
```python
result = await execute({
    "function": "get_schools_by_province",
    "province_name": "北京"
})
```

### 5. get_score_line_detail

Get detailed content of a score line page.

**Parameters:**
- `function`: "get_score_line_detail" (required)
- `url`: Page URL (required)

**Returns:**
- Title, images, PDF links, text content
- Note: Score tables are typically embedded as images

**Example:**
```python
result = await execute({
    "function": "get_score_line_detail",
    "url": "https://yz.chsi.com.cn/kyzx/fsfsx34/202503/20250312/2293356009.html"
})

# Download image URLs to view actual scores
for img in result["detail"]["images"]:
    print(f"Score table image: {img['url']}")
```

### 6. search_universities

Search for universities by name across all provinces.

**Parameters:**
- `function": "search_universities" (required)
- `name`: University name to search (required)

**Example:**
```python
result = await execute({
    "function": "search_universities",
    "name": "清华"
})
```

## Important Notes

### Score Table Format

Score line data is **not** provided as structured HTML tables. Instead, the site publishes:

1. **Images**: Score tables are rendered as images (JPG/PNG)
2. **PDFs**: Some universities provide downloadable PDF versions
3. **Text summaries**: Basic information in page text

To access actual score data:
```python
detail = await execute({
    "function": "get_score_line_detail",
    "url": "..."
})

# Images contain the score tables
for img in detail["detail"]["images"]:
    # Download and process the image
    image_url = img["url"]

# PDFs contain official documents
for pdf in detail["detail"]["pdf_links"]:
    # Download official PDF
    pdf_url = pdf["url"]
```

### Data Availability

- Historical data: 2016 - present
- Annual update cycle: New score lines published in February/March
- 34 self-determined universities: Typically announce scores earlier than national lines
- Provincial school lists: Updated throughout the year

### Province Codes

Standard Chinese administrative division codes:
- 北京: 11
- 天津: 12
- 河北: 13
- 上海: 31
- 江苏: 32
- 广东: 44
- 四川: 51
- etc.

### Query Methods

Schools indicate how to check scores:
- **此站查询** (chsi): Query on yz.chsi.com.cn
- **院校官网查询** (sch): Query on the institution's own website

Some queries require login on the source site.

## Error Handling

All functions return a consistent structure:

```python
# Success
{
    "success": True,
    # ... function-specific data ...
}

# Error
{
    "success": False,
    "error": "Error description",
    # Additional context if available
}
```

## Use Cases

1. **Compare university thresholds**: Get scores across years for a specific university
2. **Find provincial institutions**: List all graduate schools in a province
3. **Locate a university**: Search by name to find province and query method
4. **Download score tables**: Get image/PDF URLs for official score documents
5. **Track national trends**: Compare national minimum scores across years

## Technical Details

- **Host**: yz.chsi.com.cn
- **Base URL**: https://yz.chsi.com.cn
- **Province API**: https://yz.chsi.com.cn/apply/code/cjcxshouyedw/{code}.json
- **Data format**: Embedded JavaScript objects for lists, JSON API for province data
- **Score pages**: HTML with embedded images/PDFs
- **Rate limiting**: 2 requests/second recommended
- **Caching**: University lists can be cached for 24 hours