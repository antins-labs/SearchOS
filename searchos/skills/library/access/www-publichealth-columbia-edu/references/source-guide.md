# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Columbia University Mailman School of Public Health - Faculty Profile Access

This skill retrieves structured faculty profile data from Columbia University's Mailman School of Public Health website (publichealth.columbia.edu).

## Features

- **Get Profile**: Retrieve detailed information about a specific faculty member by their profile URL slug
- **Search Profiles**: Basic search functionality to find faculty by name

## Data Extracted

For each faculty profile, the skill extracts:

- **Name**: Full name with credentials (e.g., "Hernandez Stroud, JD")
- **Academic Titles**: Positions at the university (e.g., "Adjunct Assistant Professor of Health Policy and Management")
- **Bio**: Biographical summary
- **Education**: Degrees with institutions and years (parsed into individual entries)
- **Research Interests**: Areas of research focus
- **Affiliations**: External appointments and community service roles
- **Address**: Office location with formatted components
- **Links**: Social media and personal website links
- **Headshot URL**: Profile photo (when available as URL, not embedded base64)

## Usage Examples

### Get a Specific Profile

```json
{
  "function": "get_profile",
  "profile_slug": "hernandez-stroud-jd"
}
```

Response:
```json
{
  "success": true,
  "profile": {
    "name": "Hernandez Stroud, JD",
    "academic_titles": ["Adjunct Assistant Professor of Health Policy and Management"],
    "bio": "Hernandez D. Stroud is counsel at the Brennan Center for Justice...",
    "education": [
      "BA, 2010 University of Alabama at Birmingham",
      "MS, 2012 University of Pennsylvania",
      "JD, 2015 Washington and Lee University"
    ],
    "research_interests": [
      "Community Health",
      "Healthcare Policy",
      "Incarceration Prevention",
      "Maternal and Reproductive Health",
      "Substance Use"
    ],
    "affiliations": ["Counsel, Justice Program, Brennan Center for Justice at NYU School of Law"],
    "address": "722 West 168th Street, New York, NY 10032",
    "links": [
      {"text": "Twitter", "url": "https://x.com/hernandezstroud"},
      {"text": "Website", "url": "https://www.brennancenter.org/experts/hernandez-stroud"}
    ],
    "source_url": "https://www.publichealth.columbia.edu/profile/hernandez-stroud-jd"
  }
}
```

### Search for Profiles

```json
{
  "function": "search_profiles",
  "query": "Hernandez Stroud"
}
```

Note: The search function uses slug pattern matching and may not find all matches. For comprehensive faculty discovery, browse the school's faculty directory directly.

## Profile Slug Format

Profile URLs follow the pattern:
```
https://www.publichealth.columbia.edu/profile/{slug}
```

Common slug formats:
- `firstname-lastname` (e.g., `john-smith`)
- `firstname-lastname-degree` (e.g., `jane-doe-phd`)
- `firstname-middlename-lastname` (e.g., `mary-jane-wilson`)

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Profile not found",
  "status_code": 404,
  "url": "https://www.publichealth.columbia.edu/profile/invalid-slug"
}
```

## Technical Notes

- Uses direct HTTP requests (no browser automation required)
- Parses HTML using BeautifulSoup
- Handles 404 pages gracefully
- Follows redirects automatically
- Extracts structured data from Drupal-based profile pages
