# Harvard GSAS Programs Access Skill

Access graduate programs from the Harvard Kenneth C. Griffin Graduate School of Arts and Sciences (GSAS).

## Available Functions

### list_programs
List all graduate programs with pagination and filtering support.

**Parameters:**
- `page` (integer, optional): Page number for pagination (default: 0, 10 results per page)
- `degrees_offered` (string, optional): Filter by degree type. Options: "Doctor of Philosophy (PhD)", "Master of Arts (AM)", "Master of Science (SM)", "Master of Engineering (ME)", "AB/AM, AB/SM"
- `areas_of_study` (string, optional): Filter by area. Options: "Arts & Architecture", "Biological Sciences", "Engineering & Applied Sciences", "Harvard Integrated Life Sciences", "History", "Humanities", "Languages", "Mathematics", "Medical Sciences", "Physical Sciences", "Social Sciences"
- `gre_requirement` (string, optional): Filter by GRE requirement. Options: "Required", "Optional", "Not Accepted"
- `program_type` (string, optional): Filter by program type. Options: "Degree Granting", "Combined Degree", "Summer Programs", "Visiting Students"
- `search` (string, optional): Search term to filter programs by name

**Returns:**
- `results`: Array of programs with title, url, gre_requirement, and degrees_offered
- `total`: Total number of matching results
- `page`: Current page number

### get_program
Get detailed information about a specific program.

**Parameters:**
- `program_url` (string, required): Full URL or slug of the program (e.g., "african-and-african-american-studies" or full URL)

**Returns:**
- `title`: Program name
- `header_text`: Brief description
- `body`: Full program description
- `degrees`: Array of degree types with deadlines and application links
- `contact`: Contact information (name, title, email)
- `program_website`: External program website URL

### get_applying_info
Get information about the application process for degree programs.

**Returns:**
- `sections`: Array of content sections with headings and content about the application process
- `faqs`: Array of frequently asked questions with answers

## Examples

```python
# List all PhD programs
result = await execute({
    "function": "list_programs",
    "degrees_offered": "Doctor of Philosophy (PhD)"
})

# Search for physics programs
result = await execute({
    "function": "list_programs",
    "search": "physics"
})

# Get details for a specific program
result = await execute({
    "function": "get_program",
    "program_url": "computer-science"
})

# Get application information
result = await execute({
    "function": "get_applying_info"
})
```

## Source

Data is fetched from https://gsas.harvard.edu