# HKUST MSc in Business Analytics Access Skill

## Overview

This SearchOS access skill provides structured access to admission information, program details, fees, curriculum, and other relevant data from the HKUST Master of Science in Business Analytics (MSBA) program website.

## Website Analysis

### Site Structure

The HKUST MSBA website (`https://msba.hkust.edu.hk/`) is a Drupal-based site with the following key sections:

- **Admission Pages**:
  - `/admission/admission-requirements` - Entry requirements
  - `/admission/application-schedule-procedures` - Deadlines and how to apply
  - `/admission/program-fee-expenses` - Tuition and costs
  - `/admission/scholarship-financial-aids` - Financial support options

- **Program Pages**:
  - `/program/overview-schedule` - Program structure and duration
  - `/program/program-curriculum` - Courses and credits
  - `/program/graduation-degree` - Graduation requirements

- **Student Life Pages**:
  - `/student-life/class-profile` - Demographic statistics

### Data Extraction Approach

The site uses server-side rendering (Drupal) with no public JSON API detected. All content is embedded in HTML, requiring parsing with BeautifulSoup.

Key observations:
- No XHR/fetch API calls for content loading
- Content is in standard HTML structure
- Main content is within `<div class="layout-content">` or `<article>` tags
- Headings (h1-h4) provide section structure
- Fee and deadline information is in prose format (no tables detected)

## Available Functions

### 1. get_program_fees

Returns comprehensive fee information:

```python
{
    "success": True,
    "data": {
        "intake_year": "2027/28",
        "tuition_fee_hkd": "415,000",
        "caution_money_hkd": "400",
        "graduation_fee_hkd": "400",
        "visa_fee_hkd": "1,000",
        "notes": [
            "Program fee excludes books, computer equipment, software licensing",
            "Compulsory medical insurance required for non-local students"
        ]
    }
}
```

### 2. get_admission_requirements

Returns detailed admission criteria:

```python
{
    "success": True,
    "data": {
        "requirements": [
            {
                "category": "1. A Relevant First Degree",
                "details": ["Bachelor's degree from recognized institution..."]
            },
            {
                "category": "2. English Proficiency",
                "details": ["TOEFL iBT: 80+", "IELTS: 6.5 overall..."]
            }
        ],
        "key_requirements": {
            "toefl_min": "80",
            "ielts_min": "6.5"
        }
    }
}
```

### 3. get_application_schedule

Returns deadlines and application steps:

```python
{
    "success": True,
    "data": {
        "intake_year": "2027/28",
        "deadlines": [
            {
                "phase": "Phase 1",
                "full_time_deadline": "Oct 11, 2026",
                "part_time_deadline": "Dec 13, 2026",
                "year": "2027/28"
            }
        ],
        "rolling_admissions": True
    }
}
```

### 4. get_scholarships

Returns available scholarships:

```python
{
    "success": True,
    "data": {
        "scholarships": [
            {
                "name": "Admissions Scholarship",
                "description": "Merit-based scholarship...",
                "amount": "Up to half of tuition fees"
            }
        ]
    }
}
```

### 5. get_curriculum

Returns program courses:

```python
{
    "success": True,
    "data": {
        "total_credits": "30",
        "required_credits": "16",
        "required_courses": [
            {"name": "Introduction to Business Analytics", "category": "Required"}
        ],
        "elective_courses": [
            {"name": "Business Analytics in R", "category": "Elective"}
        ],
        "has_consulting_track": True
    }
}
```

### 6. get_program_overview

Returns program summary:

```python
{
    "success": True,
    "data": {
        "program_modes": ["Full-time", "Part-time"],
        "duration": {
            "full_time": "1 year",
            "part_time": "2 years"
        },
        "campus": "HKUST Clear Water Bay Campus",
        "features": [
            "Design thinking workshops",
            "Corporate consulting track",
            "Professional workshops"
        ]
    }
}
```

### 7. get_class_profile

Returns class statistics:

```python
{
    "success": True,
    "data": {
        "year": "2024-25",
        "statistics": {
            "gender_ratio": "3:2 (Female:Male)",
            "countries_represented": "10",
            "degree_disciplines": "7:2:1 (Business:Engineering:Others)"
        }
    }
}
```

### 8. search_all

Searches across all pages:

```python
execute({
    "function": "search_all",
    "query": "tuition"
})
```

Returns matching snippets from relevant pages.

### 9. get_all_info

Returns comprehensive summary:

```python
{
    "success": True,
    "data": {
        "program_fees": {...},
        "admission_requirements": {...},
        "application_schedule": {...},
        "scholarships": {...},
        "program_overview": {...}
    }
}
```

## Usage Examples

### Example 1: Get Program Fees

```python
result = await execute({"function": "get_program_fees"})
if result["success"]:
    fees = result["data"]
    print(f"Tuition: HK${fees['tuition_fee_hkd']}")
```

### Example 2: Check Admission Requirements

```python
result = await execute({"function": "get_admission_requirements"})
if result["success"]:
    for req in result["data"]["requirements"]:
        print(f"{req['category']}: {', '.join(req['details'][:2])}")
```

### Example 3: Search for Scholarships

```python
result = await execute({
    "function": "search_all",
    "query": "scholarship"
})
for match in result["data"]["results"]:
    print(f"Found in {match['page']}: {match['snippets'][0]}")
```

## Technical Implementation

### Dependencies

- `aiohttp` - Async HTTP client
- `BeautifulSoup4` - HTML parsing
- `dataclasses` - Structured data models

### Error Handling

All functions return consistent structure:

```python
{
    "success": True/False,
    "data": {...} or None,
    "error": "error message" or None,
    "source_url": "..."
}
```

### Caching

Pages are cached for 1 hour to reduce server load and improve response times.

## Notes

1. **Website Characteristics**:
   - No public API - content extracted from HTML
   - Server-side rendered (Drupal)
   - Relatively stable structure

2. **Data Accuracy**:
   - Fees and deadlines are subject to change
   - Always verify with official website for critical decisions
   - Intake year is extracted from page content

3. **Patterns Used**:
   - Regex for extracting structured data from prose
   - Heading-based section parsing
   - Graceful fallbacks for missing data

4. **Limitations**:
   - Some data formats may change between intakes
   - Table data not detected (content is in prose format)
   - Real-time availability not supported

## Changelog

- v1.0.0 (2025-01-19): Initial implementation with all core functions
  - Program fees extraction
  - Admission requirements parsing
  - Application schedule extraction
  - Scholarship information
  - Curriculum details
  - Program overview
  - Class profile statistics
  - Cross-page search functionality