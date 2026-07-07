# CollegeXpress Lists and Rankings

Access college lists and rankings from CollegeXpress.com.

## Overview

CollegeXpress hosts hundreds of curated college lists including:
- **Rankings** with metrics (library sizes, enrollment, tuition, etc.)
- **Membership lists** (Ivy League, athletic conferences, etc.)
- **Geographic lists** (schools by state, region)
- **Specialty lists** (programs, majors, campus features)

## Functions

### get_list

Fetch a specific college list or ranking.

**Parameters:**
- `url` or `list_id`: The list to fetch (one is required)
  - Full URL: `"https://www.collegexpress.com/lists/list/top-50-largest-college-libraries/747/"`
  - List ID: `"747"`
  - Slug/ID: `"top-50-largest-college-libraries/747"`
- `limit`: Optional maximum number of entries to return

**Returns:**
- List metadata (title, category, description)
- Array of college entries with:
  - For ranked lists: rank, name, location, value, profile_url
  - For simple lists: name, location, profile_url

**Example Requests:**

```json
{
  "function": "get_list",
  "url": "https://www.collegexpress.com/lists/list/top-50-largest-college-libraries/747/"
}
```

```json
{
  "function": "get_list",
  "list_id": "605"
}
```

**Example Response:**
```json
{
  "success": true,
  "url": "https://www.collegexpress.com/lists/list/top-50-largest-college-libraries/747/",
  "list_type": "ranked_with_values",
  "total_entries": 50,
  "title": "Top 50 Largest College Libraries",
  "category": "Campus Location",
  "entries": [
    {
      "rank": 1,
      "name": "Harvard University",
      "location": "Cambridge, MA",
      "value": 16832952,
      "profile_url": "https://www.collegexpress.com/college/harvard-university/2100353/details/"
    },
    {
      "rank": 2,
      "name": "University of Illinois Urbana-Champaign",
      "location": "Champaign, IL",
      "value": 13158748,
      "profile_url": "https://www.collegexpress.com/college/university-of-illinois-urbana-champaign/1100729/details/"
    }
  ]
}
```

### search_lists

Discover available CollegeXpress lists.

**Parameters:**
- `category`: Optional category filter (e.g., "campus-location", "majors")
- `limit`: Optional maximum number of results

**Example Request:**
```json
{
  "function": "search_lists",
  "limit": 20
}
```

**Example Response:**
```json
{
  "success": true,
  "total_found": 20,
  "lists": [
    {
      "id": "605",
      "slug": "the-ivy-league",
      "title": "The Ivy League",
      "url": "https://www.collegexpress.com/lists/list/the-ivy-league/605/"
    },
    {
      "id": "747",
      "slug": "top-50-largest-college-libraries",
      "title": "Top 50 Largest College Libraries",
      "url": "https://www.collegexpress.com/lists/list/top-50-largest-college-libraries/747/"
    }
  ]
}
```

## List Types

The skill automatically detects and handles three list formats:

1. **Ranked with values**: Lists where entries have numeric values (library volumes, enrollment, etc.)
   - Example: Top 50 Largest College Libraries
   - Returns: rank, name, location, value

2. **Ranked without values**: Ranked lists without numeric metrics
   - Example: Top Women's Volleyball Schools
   - Returns: rank, name, location

3. **Simple lists**: Unranked membership lists
   - Example: Ivy League, Texas Schools
   - Returns: name, location

## Popular Lists

- **605**: The Ivy League
- **747**: Top 50 Largest College Libraries
- **590**: Top Women's Volleyball Schools
- **2873**: Four-Year Colleges in Texas
- **2832**: Four-Year Colleges in California
- **3005**: Colleges With the Most School Spirit

## Data Source

Data is fetched directly from CollegeXpress.com HTML pages. Each college entry includes a link to the full CollegeXpress profile page for additional details.

## Notes

- Lists are static pages; no authentication required
- Some lists may have featured/flagged schools (indicated in original HTML)
- Profile URLs can be used to fetch additional college details (separate functionality)