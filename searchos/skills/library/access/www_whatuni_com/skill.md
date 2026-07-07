# WhatUni Course Search Access Skill

This skill provides structured access to WhatUni.com, the UK's leading university and course comparison website. It allows you to search for courses, get detailed course information, and find universities.

## Features

### 1. Search Courses (`search_courses`)

Search for university courses by subject, university, and level.

**Parameters:**
- `subject` (optional): Subject area slug, e.g., 'communication-studies', 'computer-science', 'psychology'
- `university` (optional): University name slug, e.g., 'goldsmiths-university-of-london'
- `level` (optional): 'undergraduate' or 'postgraduate' (default: 'postgraduate')
- `page` (optional): Page number for pagination (default: 1)

**Returns:**
- List of courses with titles, URLs, and course IDs
- Total number of courses found
- Page title and result count text

**Example:**
```python
result = await execute({
    'function': 'search_courses',
    'subject': 'communication-studies',
    'university': 'goldsmiths-university-of-london',
    'level': 'postgraduate'
})
# Returns courses like MRes Media & Communications, MA Media & Communications, etc.
```

### 2. Get Course Detail (`get_course_detail`)

Retrieve comprehensive information about a specific course using JSON-LD structured data.

**Parameters:** (provide either URL or slugs)
- `url` (optional): Full URL to the course page
- `course_slug` + `university_slug` (optional): URL components

**Returns:**
- Course name, description, URL
- Provider (university) information
- Course instances (duration, start dates, study mode)
- Tuition fees and pricing offers
- Modules list (if available)
- Entry requirements (if available)
- University rating and address

**Example:**
```python
result = await execute({
    'function': 'get_course_detail',
    'url': 'https://www.whatuni.com/degrees/pgdip-in-digital-media-theory/goldsmiths-university-of-london/cd/58174070/859'
})
# Returns detailed course info including duration, fees, description, etc.
```

### 3. Search Universities (`search_universities`)

Find universities by name.

**Parameters:**
- `query` (optional): Search query for university name
- `page` (optional): Page number (default: 1)

**Returns:**
- List of universities with names, URLs, and IDs

**Example:**
```python
result = await execute({
    'function': 'search_universities',
    'query': 'london'
})
# Returns universities matching 'london' in their name
```

## Data Sources

WhatUni.com provides:
- **Course listings**: Searchable database of UK university courses
- **Structured data**: JSON-LD schema.org Course and CollegeOrUniversity data
- **University profiles**: Contact info, ratings, and reviews

## Response Format

All responses include:
- `success`: Boolean indicating if the operation succeeded
- `error`: Error message if success is False
- Function-specific data fields

## Common URL Patterns

WhatUni uses consistent URL patterns:
- Course search: `/postgraduate-courses/csearch?subject={subject}&university={university}`
- Course detail: `/degrees/{course-slug}/{university-slug}/cd/{course-id}/{uni-id}`
- University profile: `/university-profile/{university-slug}/{uni-id}/`

## Notes

- Subject and university names must be provided as slugs (URL-friendly format)
- The website returns HTML with embedded JSON-LD for structured data
- Course URLs include both a course ID and university ID
- Results may be paginated for large result sets