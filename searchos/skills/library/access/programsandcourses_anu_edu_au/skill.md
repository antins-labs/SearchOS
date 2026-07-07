# ANU Programs and Courses Access Skill

Access academic program and course information from the Australian National University's Programs and Courses website (programsandcourses.anu.edu.au).

## Overview

This skill retrieves structured academic data from ANU's official course catalog, including:

**Program Information:**
- Program title, type, and college/school
- Academic codes (program code, CRICOS code, post-nominal)
- Total units and duration
- Admission requirements
- Program requirements and structure
- Compulsory and elective course lists
- Career options and learning outcomes
- Fees and scholarships information

**Course Information:**
- Course title and code
- Units and workload
- Learning outcomes
- Prerequisites and incompatibilities
- Assessment details
- Semester offerings
- Prescribed texts and assumed knowledge

## Functions

### get_program

Retrieve detailed information about an academic program.

**Parameters:**
- `code` (required): Program code (e.g., 'NELENG', 'NENES', 'BBUS')
- `year` (optional): Academic year (e.g., '2024')

**Example:**
```python
result = await execute({
    'function': 'get_program',
    'code': 'NELENG'
})
```

**Returns:**
```json
{
  "success": true,
  "url": "https://programsandcourses.anu.edu.au/program/NELENG",
  "type": "program",
  "program": {
    "title": "Master of Engineering in Electrical Engineering",
    "degree_type": "single degree",
    "college": "ANU College of Systems and Society",
    "code": "NELENG",
    "year": "current",
    "total_units": 96,
    "description": "A single two year graduate award offered by the ANU College of Systems and Society",
    "codes": {
      "Academic plan": "NELENG",
      "CRICOS code": "077326G"
    },
    "sections": {
      "Program Requirements": [...],
      "Admission Requirements": [...],
      "Learning Outcomes": [...]
    },
    "courses": [
      {"code": "ENGN6224", "name": "Fluid Mechanics and Heat Transfer", "url": "..."},
      ...
    ]
  }
}
```

### get_course

Retrieve detailed information about a specific course.

**Parameters:**
- `code` (required): Course code (e.g., 'ENGN6224', 'COMP6670', 'MATH1013')
- `year` (optional): Academic year (e.g., '2024')

**Example:**
```python
result = await execute({
    'function': 'get_course',
    'code': 'COMP6670'
})
```

**Returns:**
```json
{
  "success": true,
  "url": "https://programsandcourses.anu.edu.au/course/COMP6670",
  "type": "course",
  "course": {
    "title": "Introduction to Machine Learning",
    "code": "COMP6670",
    "year": "current",
    "college": "School of Computing",
    "units": 6,
    "description": "A graduate course offered by the School of Computing.",
    "learning_outcomes": [...],
    "requisites": [...],
    "assessment": [...],
    "workload": ["130 hours including lectures and tutorials..."],
    "sections": {
      "Learning Outcomes": [...],
      "Indicative Assessment": [...],
      "Workload": [...],
      "Requisite and Incompatibility": [...]
    }
  }
}
```

### search_programs

Get information about accessing the ANU Programs catalogue.

**Note:** The ANU catalogue page requires JavaScript for full search functionality. This function returns the catalogue URL and instructions for access.

**Parameters:**
- `query` (optional): Search query (not currently functional)
- `year` (optional): Academic year

**Example:**
```python
result = await execute({
    'function': 'search_programs',
    'year': '2024'
})
```

## URL Structure

The ANU Programs and Courses site uses the following URL patterns:

- **Current Year Programs:** `https://programsandcourses.anu.edu.au/program/{CODE}`
- **Year-Specific Programs:** `https://programsandcourses.anu.edu.au/{YEAR}/program/{CODE}`
- **Current Year Courses:** `https://programsandcourses.anu.edu.au/course/{CODE}`
- **Year-Specific Courses:** `https://programsandcourses.anu.edu.au/{YEAR}/course/{CODE}`

## Code Formats

- **Program Codes:** Typically 5-6 uppercase characters
  - Examples: NELENG, NENES, BBUS, MCOMP
  
- **Course Codes:** Typically 8 characters (4 letters + 4 digits)
  - Examples: ENGN6224, COMP6670, MATH1013

## Common Programs

| Code | Program Name |
|------|--------------|
| NELENG | Master of Engineering in Electrical Engineering |
| NENES | Master of Engineering in Energy Systems |
| MCOMP | Master of Computing |
| BBUS | Bachelor of Business Administration |
| BSC | Bachelor of Science |

## Notes

- The site may require cookie handling for some requests
- Data is retrieved from structured HTML pages
- Some pages may have slight variations in structure
- Course offerings and details may vary between years
- All data is sourced from ANU's official Programs and Courses website