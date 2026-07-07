# 大学生必备网 (dxsbb.com) Access Skill

## Overview

This skill provides structured access to Chinese college admission data from 大学生必备网 (dxsbb.com), a comprehensive educational information website that publishes university admission scores (投档分数线) and related data for universities across China.

## Data Available

The site contains:

- **投档分数线 (Admission Triage Scores)**: Minimum scores for university admission by province
- **高考分数 (Gaokao Scores)**: Province-level score distributions and cutoffs
- **一分一段 (Score Rankings)**: Student ranking tables by score
- **志愿填报 (College Application Guidance)**: Application-related information

Data is organized by:
- Province (省份): Beijing (北京), Shanghai (上海), Guangdong (广东), etc.
- Year (年份): 2018-2025
- Level (层次): Undergraduate (本科), Junior College (专科)
- Track (科类): Science/Arts (理科/文科), Physics/History (物理/历史)

## Usage Examples

### Search for Admission Scores

```python
# Find 2024 Beijing undergraduate admission scores
result = await execute({
    'function': 'search',
    'province': '北京',
    'year': '2024',
    'category': '投档分数'
})

# Returns matching articles with titles and URLs
```

### Get Detailed Article Data

```python
# Fetch complete table data from an article
result = await execute({
    'function': 'get_article',
    'url': 'https://www.dxsbb.com/news/106432.html'
})

# Returns structured table data with all admission scores
```

### Get All Articles in Category

```python
# Get all articles in the admission scores category
result = await execute({
    'function': 'get_list',
    'category_id': '1001'  # 投档分数
})

# Returns list of articles with dates and URLs
```

### Get Available Categories

```python
# List all available categories
result = await execute({
    'function': 'get_categories'
})
```

## Table Data Structure

Articles contain tabular admission score data. Note that table structures vary by article/year. Example columns:

**2023 article example (9 columns):**
```json
{
  "headers": ["序号", "院校", "专业组", "总分", "语文", "数学", "外语", "三科选考", "其他要求"],
  "data": [
    ["1", "0321", "陆军工程大学", "1", "物理", "475", "101", "77", "81", "216", ""]
  ]
}
```

**2025 article example (7 columns):**
```json
{
  "headers": ["序号", "院校代码", "院校名称", "专业组代码", "专业组名称", "总分", "备注"],
  "data": [
    ["1", "0321", "陆军工程大学", "01", "物理＋化学", "510", ""]
  ]
}
```

Since headers vary, the skill returns raw table data without imposing a fixed schema.

## Category IDs

| ID | Name | Description |
|----|------|-------------|
| 1001 | 投档分数 | Admission triage scores |
| 180 | 高考分数 | Gaokao scores and cutoffs |
| 223 | 一分一段 | Score ranking tables |
| 97 | 高考动态 | Gaokao news and updates |
| 822 | 志愿填报 | Application guidance |

## Performance Notes

- Tables can contain 1,000+ rows of structured data
- Data is returned in raw HTML - no JavaScript rendering required
- Rate limit: 2 requests/second recommended
- Table data in responses is limited to first 100 rows by default
- The `total_rows` field shows the complete row count

## Common Use Cases

1. **Find Admission Scores for a Province**
   - Search by province name and year
   - Get article URL and fetch full table data

2. **Analyze Score Trends**
   - Fetch multiple years of data for comparison
   - Extract university codes and scores

3. **Research University Requirements**
   - Get subject requirements from 专业组名称 column
   - Check minimum scores for specific universities

## Technical Notes

- Site uses standard HTML tables for data presentation
- No API or authentication required
- All content is in Chinese
- University codes (院校代码) are standardized national codes
- Data is updated annually after Gaokao results are released
- Data is returned as raw Python lists/dicts from aiohttp/BeautifulSoup (not JSON strings)