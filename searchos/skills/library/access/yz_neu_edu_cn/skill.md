# Northeastern University Graduate Admissions Skill

## Overview

This skill extracts graduate admissions data from Northeastern University's graduate admissions portal (yz.neu.edu.cn). It provides access to admission score requirements and complete program catalogs for master's degree programs.

## Host

`yz.neu.edu.cn` - 东北大学研究生招生信息网

## Available Functions

### 1. get_score_requirements

Get graduate admission score requirements (复试分数线 - the minimum scores required to proceed to the interview/retake phase).

**Parameters:**
- `url` (optional): Article URL for specific year's score requirements
  - Default: 2025 score requirements page

**Returns:**
```json
{
  "success": true,
  "url": "http://yz.neu.edu.cn/2025/0311/c5932a278797/pagem.htm",
  "title": "东北大学2025年硕士研究生招生考试考生进入复试的初试成绩基本要求",
  "score_images": [
    {
      "url": "http://yz.neu.edu.cn/_upload/article/images/...",
      "title": "【公布】东北大学2025年硕士研究生招生考试..."
    }
  ],
  "image_count": 5,
  "note": "分数要求以图片形式发布，请访问图片URL查看具体分数线"
}
```

**Note:** The score requirements are published as embedded images (scanned/published tables as JPG). The skill extracts these image URLs for further processing.

### 2. get_program_catalog

Get the complete graduate program catalog with all majors, research directions, study modes, and exam subjects.

**Parameters:**
- `url` (optional): Article URL for program catalog
  - Default: 2026 program catalog page
- `limit_results` (optional): Limit to 100 entries (default: true)
- `include_raw` (optional): Include raw table data (default: false)

**Returns:**
```json
{
  "success": true,
  "url": "http://yz.neu.edu.cn/2025/1009/c5933a293436/pagem.htm",
  "title": "东北大学2026年硕士研究生招生专业目录",
  "program_count": 352,
  "programs": [
    {
      "department": "001文法学院",
      "major_code": "120400公共管理学",
      "major_name": "",
      "research_area": "01行政管理",
      "study_mode": "(1)全日制",
      "exam_subjects": "①101思想政治理论②201英语（一）③617管理学基础④811公共经济学",
      "row_index": 1
    }
  ]
}
```

### 3. search_programs

Search for programs by keyword in department name, major code/name, or research area.

**Parameters:**
- `keyword` (required): Search keyword (e.g., "计算机", "机械", "数学")
- `limit_results` (optional): Limit to 50 entries (default: true)

**Returns:**
```json
{
  "success": true,
  "keyword": "计算机",
  "total_matches": 32,
  "matches": [
    {
      "department": "017计算机科学与工程学院",
      "major_code": "081000信息与通信工程",
      ...
    }
  ],
  "note": "找到 32 个匹配项"
}
```

## Example Usage

```python
# Get score requirements
result = await execute({
    'function': 'get_score_requirements'
})

# Get program catalog
result = await execute({
    'function': 'get_program_catalog',
    'limit_results': false  # Get all 350+ programs
})

# Search for computer science programs
result = await execute({
    'function': 'search_programs',
    'keyword': '计算机'
})

# Search by department code
result = await execute({
    'function': 'search_programs',
    'keyword': '017'  # Computer Science Department
})
```

## Data Structure

### Program Record
Each program entry contains:
- `department`: Department/college code and name (e.g., "001文法学院")
- `major_code`: Major code (e.g., "120400")
- `major_name`: Major name extracted from code field
- `research_area`: Research direction code and name (e.g., "01行政管理")
- `study_mode`: Full-time or part-time ("(1)全日制" or "(2)非全日制")
- `exam_subjects`: Examination subjects (e.g., "①101思想政治理论②201英语（一）...")
- `row_index`: Row position in original table

## Technical Details

- **HTTP Access**: Direct HTTP access works without browser automation
- **Site CMS**: Standard Chinese university CMS (sudy system)
- **Table Handling**: Proper parsing of merged cells in HTML tables
- **Score Data**: Published as images, URLs extracted for further OCR/processing if needed

## Notes

1. **Score Requirements as Images**: The admission score cutoffs are published as embedded images (not text tables). The skill extracts these image URLs for potential OCR processing.

2. **Program Catalog Structure**: The HTML table uses row spans and merged cells. The skill normalizes this into structured records, tracking the current department and major across rows with partial data.

3. **Chinese Text**: All content is in Chinese. Major codes follow the national standard format.

4. **Update Frequency**: 
   - Score requirements: Updated annually in March
   - Program catalog: Updated annually for next year's admission

## Error Handling

All functions return a consistent structure:
- `success`: boolean indicating successful operation
- `error`: error message if success is false
- Additional data fields when successful

When `function` parameter is missing or invalid, the skill returns available function names.