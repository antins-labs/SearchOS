# HKUST Postgraduate Program Catalog Scraper

This skill extracts structured academic program data from the Hong Kong University of Science and Technology (HKUST) Program & Course Catalog at `prog-crs.hkust.edu.hk`.

## Overview

The HKUST Program Catalog provides comprehensive information about postgraduate programs including:
- Program descriptions and learning outcomes
- Admission requirements (general and English language)
- Tuition fees and application fees
- Application deadlines for local and non-local students
- Curriculum details with course listings
- Credit requirements (total, core, elective)

## Supported Functions

### `get_program`

Retrieve detailed information for a specific postgraduate program.

**Parameters:**
- `url` (string): Full program page URL, e.g., `https://prog-crs.hkust.edu.hk/pgprog/2026-27/msc-fofb/`
- `program_code` (string): Program code from URL (e.g., `msc-fofb`, `msc-mark`)
- `academic_year` (string, optional): Academic year, defaults to `2026-27`
- `sections` (array, optional): Specific sections to extract:
  - `general_info` - Program title, fee, duration, contact info
  - `introduction` - Program description
  - `learning_outcomes` - Learning outcomes
  - `curriculum` - Course list and credit requirements
  - `admission_requirements` - Entry requirements
  - `application` - Application process and deadlines
- `include_courses` (boolean, default: true) - Include course details
- `include_deadlines` (boolean, default: true) - Parse application deadlines

**Returns:**
- `success`: Boolean indicating success/failure
- `data.title`: Program title
- `data.sections`: Object with section data
- `data.parsed_info`: Structured basic information
- `data.parsed_requirements`: Structured admission requirements
- `data.parsed_application`: Structured application info (fees, deadlines)

**Example:**
```json
{
  "function": "get_program",
  "program_code": "msc-fofb",
  "academic_year": "2026-27"
}
```

**Example Response:**
```json
{
  "success": true,
  "url": "https://prog-crs.hkust.edu.hk/pgprog/2026-27/msc-fofb/",
  "academic_year": "2026-27",
  "program_code": "msc-fofb",
  "data": {
    "title": "Master of Science Program in Family Office and Family Business",
    "sections": {
      "GENERAL INFORMATION": { ... },
      "CURRICULUM": {
        "courses": [
          {
            "code": "FINA 5190",
            "name": "Family Business",
            "credits": "2 Credit(s)"
          }
        ],
        "minimum_credits": 30,
        "core_credits": 10
      }
    },
    "parsed_info": {
      "award_title_en": "Master of Science in Family Office and Family Business",
      "short_name": "MSc(FOFB)",
      "mode_of_study": "Both full- and part-time",
      "program_fee": "HK$463,500",
      "program_fee_numeric": 463500
    },
    "parsed_requirements": {
      "english_language": {
        "toefl_ibt": 80,
        "ielts_overall": 6.5
      }
    },
    "parsed_application": {
      "application_fee": "HK$800",
      "deadlines": {
        "non_local": {
          "full_time": "1 Mar 2026",
          "part_time": "3 May 2026"
        },
        "local": {
          "full_time": "1 Mar 2026",
          "part_time": "3 May 2026"
        }
      }
    }
  }
}
```

### `list_programs`

Get information about browsing available programs.

**Parameters:**
- `academic_year` (string, default: `2026-27`)
- `level` (string, default: `pgprog`)

**Returns:** Catalog URL and navigation instructions.

### `search_courses`

Search for courses within a program curriculum.

**Parameters:**
- `url` or `program_code` (required)
- `academic_year` (optional)
- `search_term` (optional) - Filter courses by code or name

**Returns:** List of matching courses with credit information.

## Data Extraction Structure

The skill extracts the following structured data:

### Basic Information
- Award title (English and Chinese)
- Program short name/code
- Mode of study (full-time/part-time)
- Duration for each mode
- Program fee (with parsed numeric value)
- Offering department
- Program advisor/director
- Website
- Enquiry email

### Curriculum
- Minimum credit requirement
- Core course credits
- Elective credits
- Complete course list with:
  - Course code
  - Course name
  - Credit value
  - Description (when available)

### Admission Requirements
- General admission requirements
- English language requirements (TOEFL/IELTS scores)
- Additional requirements (GMAT/GRE, work experience)

### Application Information
- Application fee
- Application deadlines by:
  - Applicant type (local/non-local)
  - Mode of study (full-time/part-time)

## Program Codes

Common HKUST MSc program codes include:
- `msc-fofb` - Family Office and Family Business
- `msc-mark` - Marketing
- `msc-finc` - Finance
- `msc-ecmt` - Economics
- `msc-acct` - Accounting
- `msc-ba` - Business Analytics
- `msc-isom` - Information Systems Management

## Rate Limits

- 2 requests per second
- 30 requests per minute

## Caching

Responses are cached for 1 hour by default.

## Notes

1. **Server-Side Rendering**: The site uses static HTML generation without a REST API, requiring HTML parsing.

2. **URL Pattern**: Programs follow the URL pattern `/pgprog/{year}/{program_code}/`

3. **Course Details**: While course details are available via AJAX endpoints (`/program/ajax/courseInfo.php`), the skill extracts course information from the main page which contains all necessary data.

4. **Dynamic Navigation**: The catalog browsing interface uses JavaScript, so `list_programs` returns a link for manual browsing rather than a full program list.

5. **Multiple Languages**: Program titles may include both English and Chinese versions.

## Error Handling

The skill returns structured errors:
- `404`: Program not found (invalid program code or URL)
- Network errors with details
- Missing required parameters

## Dependencies

This skill requires:
- `aiohttp` for HTTP requests
- `beautifulsoup4` for HTML parsing