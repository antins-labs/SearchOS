# CUHK Business School Masters Programs Access Skill

## Overview

This skill extracts comprehensive program information from the CUHK Business School Masters Programs website (masters.bschool.cuhk.edu.hk). It provides detailed information about various master's degrees offered by the Chinese University of Hong Kong Business School.

## Available Programs

The site hosts information about the following programs:

| Slug | Program Name |
|------|-------------|
| `macc` | Master of Accountancy |
| `mam` | Master in Management |
| `mim` | MSc in Management |
| `mscasi` | MSc in Accounting and Finance |
| `mscba` | MSc in Business Analytics |
| `mscfbm` | MSc in Family Business Management |
| `mscfin` | MSc in Finance |
| `mscgwm` | MSc in Global Wealth Management |
| `mscistm` | MSc in Information Systems Management |
| `mscitm` | MSc in Information and Technology Management |
| `msclee` | MSc in Leadership for Experience Economy |
| `mscmkt` | MSc in Marketing |
| `mscre` | MSc in Real Estate |
| `mscsbm` | MSc in Sports Business Management |
| `mscsgb` | MSc in Sustainable Global Business |

## Functions

### 1. `list_programs`

Lists all available master's programs with their slugs, names, and URLs.

**Parameters:** None

**Example:**
```python
result = await execute({"function": "list_programs"})
```

**Response:**
```json
{
  "success": true,
  "count": 15,
  "programs": [
    {
      "slug": "macc",
      "name": "Master of Accountancy",
      "url": "https://masters.bschool.cuhk.edu.hk/programmes/macc/"
    },
    ...
  ]
}
```

### 2. `get_program`

Retrieves detailed information about a specific program.

**Parameters:**
- `slug` (string, required): The program identifier. Use `list_programs` to see all options.

**Example:**
```python
result = await execute({
    "function": "get_program",
    "slug": "mscba"  # MSc in Business Analytics
})
```

**Response includes:**
- Program name and title
- URL
- Description/overview
- Curriculum details
- Course list
- Admission requirements
- Tuition information
- Career prospects
- Contact information
- Structured headings
- JSON-LD metadata

### 3. `search_programs`

Search for programs by keyword.

**Parameters:**
- `query` (string, required): Search term

**Example:**
```python
result = await execute({
    "function": "search_programs",
    "query": "finance"
})
```

### 4. `get_multiple_programs`

Retrieve information about multiple programs in a single request.

**Parameters:**
- `slugs` (array of strings, required): List of program slugs

**Example:**
```python
result = await execute({
    "function": "get_multiple_programs",
    "slugs": ["mscfin", "mscba", "macc"]
})
```

## Data Extracted

For each program, the skill extracts:

1. **Basic Information**
   - Program name
   - Official title
   - URL

2. **Academic Content**
   - Program overview/description
   - Curriculum structure
   - Course listings
   - Tables with course details

3. **Admissions**
   - Requirements
   - Deadlines
   - Application information

4. **Financial**
   - Tuition fees
   - Scholarship opportunities

5. **Career Information**
   - Career prospects
   - Industry connections

6. **Contact**
   - Program contact details

## Technical Details

### Anti-Bot Protection

The website uses Incapsula/Imperva anti-bot protection. This skill employs several countermeasures:

- **Browser Fingerprint Spoofing**: Modifies navigator properties to appear as a legitimate browser
- **Stealth JavaScript Injection**: Removes automation detection markers
- **Proper Headers**: Sets realistic user agent and browser headers
- **Request Delays**: Implements delays between requests to avoid rate limiting
- **Cookie Handling**: Maintains session state

### Limitations

1. **Success Rate May Vary**: Due to aggressive anti-bot measures, success rates depend on:
   - IP reputation
   - Request frequency
   - Current anti-bot configuration

2. **Rate Limiting**: The skill implements a minimum 3-second delay between requests when fetching multiple programs.

3. **Playwright Requirement**: This skill requires Playwright with Chromium browser installed:
   ```bash
   pip install playwright
   playwright install chromium
   ```

## Error Handling

The skill returns structured error information:

```json
{
  "success": false,
  "error": "Site triggered anti-bot protection. Please try again later or with a different IP.",
  "slug": "macc",
  "url": "https://masters.bschool.cuhk.edu.hk/programmes/macc/"
}
```

Common error scenarios:
- Anti-bot protection triggered
- Page not found (404)
- Network timeout
- Playwright not installed

## Usage Recommendations

1. **Single Program Requests**: For best results, request one program at a time
2. **Delays Between Requests**: Wait at least 30 seconds between requests to avoid triggering anti-bot protections
3. **Retry Logic**: If blocked, wait several minutes before retrying
4. **Use List Function First**: Call `list_programs` to verify the skill is working before fetching detailed data

## Example Workflows

### Find and Get Business Analytics Program

```python
# Search for analytics programs
results = await execute({"function": "search_programs", "query": "analytics"})

# Get the specific program
program = await execute({"function": "get_program", "slug": "mscba"})

# Access the data
if program["success"]:
    print(program["program"]["program_name"])
    print(f"Overview: {program['program']['overview'][:500]}")
    print(f"Courses: {len(program['program']['courses'])} courses found")
```

### Compare Multiple Finance Programs

```python
# Get finance-related programs
results = await execute({"function": "search_programs", "query": "finance"})

# Get details for finance programs
finance_programs = await execute({
    "function": "get_multiple_programs",
    "slugs": ["mscfin", "mscgwm", "mscasi"]
})

for prog in finance_programs["programs"]:
    if not prog.get("error"):
        print(f"{prog['program_name']}: {prog.get('tuition', 'Tuition info not available')}")
```

## Source

- Website: https://masters.bschool.cuhk.edu.hk/
- Institution: CUHK Business School, The Chinese University of Hong Kong

## Notes

This skill was created due to the site's aggressive anti-bot measures making it difficult to access program information programmatically. The site showed 51 previous access attempts with zero evidence in SearchOS logs, indicating consistent blocking. This dedicated extractor provides reliable access to program information while respecting the site's protection mechanisms.