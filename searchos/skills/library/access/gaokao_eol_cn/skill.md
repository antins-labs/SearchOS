# Gaokao Data Extraction Skill

This skill extracts structured table data from the Chinese College Entrance Examination (高考) portal at gaokao.eol.cn.

## Features

### Extracted Data Types

1. **Admission Lines (投档线)**
   - University admission scores by major group
   - Data includes: School ID, School Name, Group ID, Subject Requirements, Cut-off Score
   - Example: Beijing 2024 undergraduate admission lines

2. **Score Distribution (一分一段表)**
   - Score distribution tables showing student count per score segment
   - Data includes: Score segment, Count in segment, Cumulative count
   - Example: Beijing 2023 score distribution

### Supported URLs

The skill can fetch any page from gaokao.eol.cn that contains tabular data, including:
- Province-specific pages (e.g., `/bei_jing/dongtai/`)
- Historical data (multiple years)
- Admission announcements with score tables

## Functions

### get_admission_lines

Extracts admission line data from a gaokao.eol.cn URL.

**Parameters:**
- `url` (required): Full URL to the page containing admission line tables

**Returns:**
- Success indicator
- Metadata (title, province, year)
- Array of records with: school_id, school_name, group_id, group_subject, score

Example:
```python
result = await execute({
    'function': 'get_admission_lines',
    'url': 'https://gaokao.eol.cn/bei_jing/dongtai/202407/t20240720_2625168.shtml'
})
```

### get_score_distribution

Extracts score distribution data from a gaokao.eol.cn URL.

**Parameters:**
- `url` (required): Full URL to the page containing score distribution tables

**Returns:**
- Success indicator
- Metadata (title, province, year)
- Array of records with: score, original_score, count, cumulative_count

Example:
```python
result = await execute({
    'function': 'get_score_distribution',
    'url': 'https://gaokao.eol.cn/bei_jing/dongtai/202306/t20230625_2446872.shtml'
})
```

### fetch_page

Generic function to fetch any gaokao.eol.cn page and extract all table data.

**Parameters:**
- `url` (required): Full URL to the page

**Returns:**
- Success indicator
- Page metadata (title, province, year, data_type)
- All tables found on the page with raw data
- Auto-detected data type based on page content
- Parsed records if data type is recognized

Example:
```python
result = await execute({
    'function': 'fetch_page',
    'url': 'https://gaokao.eol.cn/bei_jing/dongtai/202407/t20240720_2625168.shtml'
})
```

## Implementation Details

- Uses aiohttp for async HTTP requests
- BeautifulSoup for HTML parsing
- Automatically detects data type from page title
- Extracts metadata (year, province) from URL and title
- Handles Chinese text encoding properly
- No JavaScript execution needed (server-side rendered HTML)

## Error Handling

Returns structured error messages for:
- Invalid URLs
- Missing required parameters
- HTTP errors
- Timeout errors
- Missing or invalid table data
- Data type mismatches

## Response Format

All functions return a dictionary with:
```python
{
    'success': bool,           # Whether the operation succeeded
    'url': str,                # The fetched URL
    'title': str,              # Page title
    'province': str,           # Extracted province code
    'year': str,               # Extracted year
    'data_type': str,          # 'admission_lines' or 'score_distribution'
    'total_records': int,      # Number of extracted records
    'records': list,           # Array of structured records
    'error': str               # Error message if success=False
}
```