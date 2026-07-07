# Prospects.ac.uk Course Data Access Skill

## Overview

This skill extracts postgraduate course information from [Prospects.ac.uk](https://www.prospects.ac.uk), the UK's official graduate careers website. It parses HTML pages to retrieve structured course data including entry requirements, fees, duration, contact details, and related courses.

## Data Source

- **Host**: www.prospects.ac.uk
- **Content Type**: Postgraduate course listings for UK universities
- **Access Method**: Direct HTTP requests with HTML parsing
- **No API Required**: All data is extracted from publicly accessible HTML pages

## Supported Functions

### `get_course`

Fetch and parse a single course page.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | Full URL to the Prospects course page |
| `timeout` | integer | No | Request timeout in seconds (default: 30) |

**URL Format:**
```
https://www.prospects.ac.uk/universities/{institution-slug}-{institution-id}/{department-slug}-{department-id}/courses/{course-slug}-{course-id}
```

**Example:**
```python
result = await execute({
    "function": "get_course",
    "url": "https://www.prospects.ac.uk/universities/goldsmiths-university-of-london-3836/media-and-communications-9471/courses/script-writing-24120"
})
```

### `get_courses`

Fetch and parse multiple course pages concurrently.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `urls` | array | Yes | List of course page URLs |
| `timeout` | integer | No | Request timeout per page (default: 30) |
| `max_concurrent` | integer | No | Max concurrent requests (default: 5) |

**Example:**
```python
result = await execute({
    "function": "get_courses",
    "urls": [
        "https://www.prospects.ac.uk/universities/goldsmiths-university-of-london-3836/media-and-communications-9471/courses/script-writing-24120",
        "https://www.prospects.ac.uk/universities/goldsmiths-university-of-london-3836/media-and-communications-9471/courses/filmmaking-cinematography-112152"
    ]
})
```

## Output Structure

### Success Response

```json
{
  "url": "https://www.prospects.ac.uk/...",
  "title": "Script Writing",
  "description": "Discover entry requirements, content, fees...",
  "url_info": {
    "institution_slug": "goldsmiths-university-of-london",
    "institution_id": "3836",
    "department_slug": "media-and-communications",
    "department_id": "9471",
    "course_slug": "script-writing",
    "course_id": "24120"
  },
  "json_ld": {
    "@type": "Course",
    "name": "Script Writing",
    "provider": {
      "@type": "Organization",
      "name": "Goldsmiths, University of London"
    }
  },
  "institution": {
    "name": "Goldsmiths, University of London",
    "department": "Media and Communications",
    "website": "http://www.gold.ac.uk/..."
  },
  "course": {
    "qualifications": "MA",
    "duration": "12 months",
    "attendance": "full-time",
    "entry_requirements": "You will be considered for this programme...",
    "content": "The skills of storytelling are timeless...",
    "fees": {
      "uk_home": "£10350",
      "international": "£22640"
    },
    "contact": {
      "name": "Course Enquiries",
      "email": "course-info@gold.ac.uk",
      "phone": "+44 (0)20 7078 5300"
    }
  },
  "sections": {
    "Entry requirements": "You will be considered...",
    "Course content": "The skills of storytelling...",
    "Fees and funding": "UK students Home - full-time...",
    "Qualification, course duration and attendance options": "MA full time 12 months..."
  },
  "related_courses": [
    {
      "title": "Filmmaking (Cinematography)",
      "url": "https://www.prospects.ac.uk/..."
    }
  ]
}
```

### Error Response

```json
{
  "error": "Request failed",
  "status": 404,
  "message": "HTTP 404",
  "url": "https://www.prospects.ac.uk/..."
}
```

## Data Extracted

| Field | Source | Description |
|-------|--------|-------------|
| `title` | `<h1>` | Course title |
| `description` | `<meta name="description">` | Page meta description |
| `url_info` | URL parsing | IDs and slugs from URL |
| `json_ld` | Schema.org | Structured course data |
| `institution` | Definition lists | University and department |
| `qualifications` | Definition lists | Degree type (MA, MSc, etc.) |
| `duration` | Duration section | Course length |
| `attendance` | Duration section | full-time/part-time |
| `entry_requirements` | Entry requirements section | Admission criteria |
| `content` | Course content section | Detailed description |
| `fees` | Fees section | UK and international fees |
| `contact` | Contact section | Name, email, phone |

## URL Structure

Course URLs follow this pattern:
```
/universities/{institution-name}-{institution-id}/{department-name}-{department-id}/courses/{course-name}-{course-id}
```

Example breakdown:
- **Institution**: `goldsmiths-university-of-london-3836` (name + ID)
- **Department**: `media-and-communications-9471` (name + ID)
- **Course**: `script-writing-24120` (name + ID)

The numeric IDs are critical for uniquely identifying resources.

## Notes

1. **No Search Function**: The site uses dynamic JavaScript loading for search. This skill only supports direct course URL access.

2. **URL Discovery**: To find course URLs, you may need to:
   - Browse the site manually
   - Use search engines with `site:prospects.ac.uk/courses/`
   - Follow links from institution pages

3. **Rate Limiting**: Default rate limit is 2 requests/second with 5 concurrent connections to avoid overwhelming the server.

4. **Data Availability**: Not all courses have all fields populated. The skill gracefully handles missing data.

5. **Fee Information**: Fees are extracted from the Fees and funding section. Format and availability may vary by institution.

## Use Cases

- **Course Research**: Aggregate course details for comparison
- **Fee Tracking**: Monitor tuition fee changes
- **Contact Information**: Collect admissions contact details
- **Entry Requirements**: Analyze admission criteria across courses
- **Link Discovery**: Use `related_courses` to discover similar programs

## Error Handling

The skill returns structured error responses rather than raising exceptions:

| Error Type | Description |
|------------|-------------|
| `Missing function` | No function specified in params |
| `Missing URL` | No URL provided for `get_course` |
| `Missing URLs` | No URLs provided for `get_courses` |
| `Invalid domain` | URL is not from prospects.ac.uk |
| `Invalid URL` | URL doesn't match course page pattern |
| `Request failed` | HTTP error or timeout |
| `Empty response` | Page returned no content |
| `Invalid page` | Page doesn't contain expected course data |

## Dependencies

- `aiohttp` - Async HTTP client
- `beautifulsoup4` - HTML parsing
- Standard library: `asyncio`, `json`, `re`, `urllib.parse`