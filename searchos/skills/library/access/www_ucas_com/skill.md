# UCAS Course Access Skill

## Overview

This skill provides access to UK university and college course information from UCAS (Universities and Colleges Admissions Service). It can fetch detailed course information including titles, providers, qualifications, entry requirements, fees, contact details, and course statistics.

## Functions

### get_course

Fetches comprehensive details for a specific course by its UCAS course ID.

**Parameters:**
- `course_id` (required): UCAS course identifier in UUID format (e.g., "18f73fdf-0804-2e30-cf22-f66710164e4f")
- `course_slug` (optional): URL-friendly course name for building complete URLs (e.g., "media-and-communication")

**Returns:**
- Course title and URL
- Provider/institution name
- Course summary and description
- Entry requirements
- Fees and funding information
- Sponsorship information
- Study options (qualifications, modes, durations)
- Campus locations
- Contact details (email, phone)
- Structured data from Algolia (subjects, start dates, locations, etc.)
- Unistats data (NSS scores, employment rates, salaries) when available

**Example:**
```python
result = await execute({
    "function": "get_course",
    "course_id": "18f73fdf-0804-2e30-cf22-f66710164e4f",
    "course_slug": "media-and-communication"
}, ctx)
```

### search_courses

Searches for courses using keywords and filters via UCAS's Algolia-powered search.

**Parameters:**
- `query` (optional): Search keywords (course title, subject, etc.)
- `provider` (optional): University/college name filter
- `study_level` (optional): Study level filter - "Undergraduate" or "Postgraduate"
- `max_results` (optional, default=20): Maximum number of results to return (max 100)

**Note:** At least one of `query` or `provider` must be provided.

**Returns:**
- Total number of matching courses
- Array of course summaries with:
  - Course ID and URL
  - Title and qualification
  - Provider/institution
  - Study level and mode
  - Duration and location
  - Start date and subjects

**Example:**
```python
result = await execute({
    "function": "search_courses",
    "query": "computer science",
    "study_level": "Undergraduate",
    "max_results": 10
}, ctx)
```

## Data Sources

This skill uses:
1. **HTML page scraping** for rich course descriptions, entry requirements, and contact details
2. **Algolia search API** for structured course metadata and search functionality
3. **UCAS Unistats API** for course statistics (satisfaction scores, employment data)

## Notes

- Course IDs are UUIDs that can be discovered through search or from UCAS URLs
- The skill handles both plain HTML extraction and structured JSON data from APIs
- Postgraduate courses may have fewer statistics available in Unistats
- Some course details (like entry requirements) may be specific to course options rather than the overall course