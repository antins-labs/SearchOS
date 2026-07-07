# Goldsmiths, University of London - Course Finder Access Skill

Access course information and academic programs at Goldsmiths, University of London through their course finder system.

## Overview

Goldsmiths uses a Funnelback-powered course finder that returns search results as HTML. This skill provides direct HTTP access to search and retrieve course information, including:

- Course search with multiple filter options
- Detailed course information from individual course pages
- Department/school information
- Available filter options

## Functions

### search_courses

Search for courses with optional filters and pagination.

**Parameters:**
- `function`: "search_courses" (required)
- `query`: Search query (optional)
- `school`: Filter by school (see get_filters for valid values)
- `course_level`: Filter by course level (see get_filters for valid values)
- `study_mode`: Filter by study mode (optional)
- `academic_area`: Filter by academic area (optional)
- `page`: Page number, default 1 (optional)

**Example:**
```python
result = await execute({
    "function": "search_courses",
    "school": "Media, Communications and Cultural Studies",
    "page": 1
})
```

**Returns:**
```json
{
  "success": true,
  "total_on_page": 10,
  "current_page": 1,
  "total_pages": 4,
  "has_next_page": true,
  "courses": [
    {
      "title": "BA (Hons) Media & Communications",
      "url": "https://www.gold.ac.uk/ug/ba-media-communications/",
      "summary": "Bringing together media practice and communications theory...",
      "level": "Undergraduate",
      "image_url": "https://..."
    }
  ]
}
```

### get_course_details

Get detailed information about a specific course.

**Parameters:**
- `function`: "get_course_details" (required)
- `url`: Full URL of the course page (required)

**Example:**
```python
result = await execute({
    "function": "get_course_details",
    "url": "https://www.gold.ac.uk/ug/ba-media-communications/"
})
```

**Returns:**
```json
{
  "success": true,
  "course": {
    "url": "https://www.gold.ac.uk/ug/ba-media-communications/",
    "course_code": "P300",
    "name": "BA Media & Communications",
    "description": "Bringing together media practice...",
    "prerequisites": "CCC",
    "credits": 360,
    "award": "BA",
    "study_mode": "Full-time",
    "start_date": "2025-09-22",
    "end_date": "2028-06-19",
    "location": "Goldsmiths, University of London",
    "provider": "Goldsmiths, University of London"
  }
}
```

### get_filters

Get all available filter options for course search.

**Parameters:**
- `function`: "get_filters" (required)

**Example:**
```python
result = await execute({
    "function": "get_filters"
})
```

**Returns:**
```json
{
  "success": true,
  "filters": {
    "School|courseschool": {
      "display_name": "School",
      "options": [
        {"label": "Art", "value": "Art"},
        {"label": "Computing", "value": "Computing"},
        {"label": "Media, Communications and Cultural Studies", "value": "Media, Communications and Cultural Studies"}
      ]
    },
    "Course level|courselevel": {
      "display_name": "Course level",
      "options": [
        {"label": "Undergraduate and Integrated Degrees (BA, BSc, BMus, LLB)", "value": "Undergraduate and Integrated Degrees<br />(BA, BSc, BMus, LLB)"},
        {"label": "Masters (MA, MSc, MMus, MRes, LLM)", "value": "Masters<br />(MA, MSc, MMus, MRes, LLM)"}
      ]
    }
  }
}
```

### get_department_info

Get information about a department or school.

**Parameters:**
- `function`: "get_department_info" (required)
- `slug`: URL slug of the department (required)

**Example:**
```python
result = await execute({
    "function": "get_department_info",
    "slug": "media-communications"
})
```

## Available Schools

- Art
- Computing
- Creative Management
- Design
- Global Change
- Media, Communications and Cultural Studies
- Mind, Body and Society
- Music, English and Theatre

## Available Course Levels

- Undergraduate and Integrated Degrees (BA, BSc, BMus, LLB)
- Masters (MA, MSc, MMus, MRes, LLM)
- Graduate Diplomas, Postgraduate Diplomas and Certificates (GDip, PGDip and PGCert)
- Research degrees (PhD, MPhil)
- PGCE
- International Foundation Certificates (IFC)

## Technical Notes

1. **Search System**: The course finder uses a Funnelback-powered search system that returns HTML results.

2. **Filter Values**: Filter values for `course_level` contain HTML `<br />` tags. These should be preserved when passing as parameters. Use the `get_filters` function to get the exact values.

3. **Pagination**: Uses `start_rank` parameter (1, 11, 21, etc.) with 10 results per page.

4. **Course Detail Pages**: Extract JSON-LD structured data with the Course schema.org type for comprehensive course information.

5. **Rate Limiting**: Implemented with reasonable delays between requests.

## Common Use Cases

### Get all courses in a school
```python
# Get all Media, Communications and Cultural Studies courses
result = await execute({
    "function": "search_courses",
    "school": "Media, Communications and Cultural Studies"
})
```

### Search for a specific course
```python
# Search for journalism courses
result = await execute({
    "function": "search_courses",
    "query": "journalism"
})
```

### Get undergraduate courses only
```python
result = await execute({
    "function": "search_courses",
    "course_level": "Undergraduate and Integrated Degrees<br />(BA, BSc, BMus, LLB)"
})
```

### Combine multiple filters
```python
result = await execute({
    "function": "search_courses",
    "school": "Computing",
    "course_level": "Masters<br />(MA, MSc, MMus, MRes, LLM)",
    "study_mode": "Full-time"
})
```

### Get detailed course information
```python
# First search for courses
search_result = await execute({
    "function": "search_courses",
    "school": "Media, Communications and Cultural Studies"
})

# Then get details for a specific course
if search_result['success'] and search_result['courses']:
    course_url = search_result['courses'][0]['url']
    details = await execute({
        "function": "get_course_details",
        "url": course_url
    })
```

## Error Handling

All functions return a consistent response structure:
- `success`: Boolean indicating if the operation succeeded
- `error`: Error message if `success` is false
- Additional data fields if `success` is true