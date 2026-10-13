# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# CMU Statistics & Data Science Faculty Profile Access

This skill retrieves faculty profile data from Carnegie Mellon University's Statistics & Data Science department website at `www.cmu.edu/dietrich/statistics-datascience/people/faculty/`.

## Features

### Get Faculty List
Retrieve all faculty members in the department, optionally filtered by last name initial.

```json
{
  "function": "get_faculty_list",
  "last_initial": "l"
}
```

Returns a list of faculty with:
- `name`: Full name
- `title`: Position/title
- `profile_url`: Link to detailed profile
- `last_initial`: First letter of last name
- `visible`: Whether visible in default view

### Get Faculty Profile
Retrieve detailed information for a specific faculty member.

```json
{
  "function": "get_faculty_profile",
  "url": "ann-lee"
}
```

Or with full URL:
```json
{
  "function": "get_faculty_profile",
  "url": "https://www.cmu.edu/dietrich/statistics-datascience/people/faculty/ann-lee.html"
}
```

Returns detailed profile with:
- `name`: Full name
- `title`: Position/title
- `description`: Research interests summary
- `research_areas`: List of research areas
- `email`: Email address
- `phone`: Phone number
- `office`: Office location
- `website`: Personal website (if available)
- `department`: Statistics & Data Science
- `college`: Dietrich College of Humanities and Social Sciences
- `university`: Carnegie Mellon University

### Search Faculty
Search for faculty by name.

```json
{
  "function": "search_faculty",
  "query": "lee"
}
```

Returns matching faculty entries.

## Data Source

The skill scrapes data directly from CMU's public faculty pages. The department website includes:
- A faculty listing page with filterable bios by last name initial
- Individual profile pages with detailed contact and research information

## Notes

- Email addresses on CMU's site are obfuscated using `(through)` instead of `@`. This skill converts them to standard email format.
- Some faculty members may be hidden in the default view on the website but are still extracted by this skill.
- Research areas are extracted from the page's metadata tags.
