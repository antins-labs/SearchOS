# UQ Study Portal Access Skill

Extract comprehensive program information from the University of Queensland's study portal (study.uq.edu.au).

## Overview

This skill provides access to UQ's degree and program catalog, including:
- Program details (title, code, type, duration)
- Fees and locations
- Entry requirements
- Career outcomes
- Accreditation information
- Course structures

## Data Sources

The skill uses two data sources:

1. **JSON:API Endpoint** (`/jsonapi/uq_program/uq_program`)
   - Provides program listings with basic information (code, title, year)
   - Enables efficient searching and filtering
   - Returns structured JSON data

2. **HTML Pages** (`/study-options/programs/{slug}-{code}`)
   - Provides detailed program information
   - Includes fees, entry requirements, careers, and more
   - Parsed using BeautifulSoup

## Functions

### get_program

Get detailed information about a specific program.

**Parameters:**
- `program_code` (required): The program code (e.g., "5743")
- `year` (optional): Academic year filter (e.g., 2025, 2026)

**Returns:**
```json
{
  "url": "https://study.uq.edu.au/study-options/programs/master-civil-engineering-professional-5743",
  "program_code": "5743",
  "title": "Master of Civil Engineering (Professional)",
  "year": 2025,
  "description": "Develop the specialist knowledge and technical skills...",
  "program_type": "Masters by coursework",
  "campus": "St Lucia",
  "duration": "2 Years",
  "annual_fee": "58056",
  "cricos_code": "108880K",
  "aqf_level": 9,
  "start_semesters": "Semester 1 (23 Feb, 2026), Semester 2 (27 Jul, 2026)",
  "overview": "...",
  "highlights": ["...", "..."],
  "entry_requirements": "...",
  "careers": ["Civil engineer"],
  "accreditation": ["Engineers Australia"],
  "professional_memberships": ["Engineers Australia"],
  "learning_methods": ["Lectures", "Tutorials", "Laboratory work", "Seminars"],
  "sample_courses": ["Advanced Environmental Monitoring Techniques..."],
  "course_links": [...]
}
```

### search_programs

Search for programs by title or code.

**Parameters:**
- `title` (optional): Search term for title matching (CONTAINS search)
- `program_code` (optional): Exact program code
- `year` (optional): Filter by academic year
- `limit` (optional): Maximum results (default: 50)

**Returns:**
```json
{
  "programs": [
    {
      "id": "c8a33c84-e7a0-4db3-87df-4c6f8a175ac0",
      "code": "5743",
      "title": "Master of Civil Engineering (Professional)",
      "year": 2025
    }
  ],
  "count": 1,
  "has_more": false
}
```

### list_programs

List all available programs.

**Parameters:**
- `limit` (optional): Maximum results (default: 100)

**Returns:**
```json
{
  "programs": [...],
  "count": 100
}
```

## Usage Examples

### Get program details

```python
result = await execute({
    "function": "get_program",
    "program_code": "5743"
})
```

### Search for engineering programs

```python
result = await execute({
    "function": "search_programs",
    "title": "engineering",
    "limit": 10
})
```

### Get program for specific year

```python
result = await execute({
    "function": "get_program",
    "program_code": "5743",
    "year": 2026
})
```

## Supported Program Types

- Bachelor's degrees
- Master's degrees (coursework and research)
- Graduate certificates and diplomas
- Doctoral programs
- Non-award programs

## Campus Locations

- **St Lucia**: Main campus in Brisbane
- **Gatton**: Agriculture and veterinary science campus
- **Herston**: Health and medicine campus
- **Digital**: Online programs
- **Online**: Fully online delivery

## Data Fields

| Field | Source | Description |
|-------|--------|-------------|
| program_code | API/HTML | Official program code |
| title | API/HTML | Program name |
| year | API | Academic year |
| program_type | HTML | Type (Bachelor, Master, etc.) |
| description | HTML | Brief description |
| overview | HTML | Detailed overview |
| duration | HTML | Study duration |
| campus | HTML | Delivery location |
| annual_fee | HTML | Annual tuition fee (AUD) |
| cricos_code | HTML | International student code |
| aqf_level | HTML | Australian Qualifications Framework level |
| start_semesters | HTML | Available intake periods |
| entry_requirements | HTML | Admission requirements |
| highlights | HTML | Key program features |
| careers | HTML | Career outcomes |
| accreditation | HTML | Professional accreditation |

## Notes

- Programs may have multiple year versions with different details
- Fees are indicative annual tuition for international students
- Entry requirements vary by student type (domestic/international)
- Course structures may change between years
- Some programs offer part-time or online study options

## Error Handling

The skill returns structured errors without raising exceptions:

```json
{
  "error": "Program with code 9999 not found",
  "program_code": "9999"
}
```

Common errors:
- Program not found (invalid code)
- Page not accessible (network issues)
- Invalid parameters