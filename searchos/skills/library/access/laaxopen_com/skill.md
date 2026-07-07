# LAAX Open Results Skill

Access snowboard and freeski competition results from the LAAX OPEN event via the site's WordPress REST API.

## Capabilities

This skill provides access to:
- **Complete competition results** from LAAX OPEN snowboard and freeski events
- **Athlete rankings** for finals rounds (halfpipe and slopestyle)
- **Podium results** with gold, silver, and bronze medalists
- **Historical data** from multiple years (2024, 2025, 2026)

## Available Functions

### `list_results`
List all available competition results, optionally filtered by year.

**Parameters:**
- `year` (optional): Filter by year (e.g., 2025, 2026)

**Example:**
```python
# List all results
execute({'function': 'list_results'})

# List 2025 results only
execute({'function': 'list_results', 'year': 2025})
```

**Returns:**
- Array of events with basic info and top 3 podium finishers

---

### `get_event`
Get detailed results for a specific event.

**Parameters:**
- `event_id` (optional): WordPress post ID of the event
- `slug` (optional): Event URL slug

**Example:**
```python
# Get by ID
execute({'function': 'get_event', 'event_id': 4083})

# Get by slug
execute({'function': 'get_event', 'slug': 'finals-halfpipe-snowboard-men-2'})
```

**Returns:**
- Full athlete rankings for the event
- FIS detailed results PDF link (if available)

---

### `search`
Search events by discipline, sport, gender, or year.

**Parameters:**
- `discipline` (optional): 'halfpipe' or 'slopestyle'
- `sport` (optional): 'snowboard' or 'freeski'
- `gender` (optional): 'men' or 'women'
- `year` (optional): Filter by year

**Example:**
```python
# Find all snowboard halfpipe events
execute({'function': 'search', 'sport': 'snowboard', 'discipline': 'halfpipe'})

# Find women's events from 2026
execute({'function': 'search', 'gender': 'women', 'year': 2026})
```

---

### `get_years`
Get list of available years with competition results.

**Example:**
```python
execute({'function': 'get_years'})
```

## Data Structure

### Event Data
```json
{
  "id": 4083,
  "title": "Finals Halfpipe Snowboard Men",
  "slug": "finals-halfpipe-snowboard-men-2",
  "date": "2025-08-13T14:10:43",
  "sport": "snowboard",
  "discipline": "halfpipe",
  "gender": "men",
  "phase": "finals",
  "podium": [
    {"rank": 1, "name": "JAMES Scotty", "is_medalist": true},
    {"rank": 2, "name": "HIRANO Ruka", "is_medalist": true},
    {"rank": 3, "name": "HIRANO Ayumu", "is_medalist": true}
  ],
  "fis_pdf_url": "https://laaxopen.com/wp-content/uploads/2025/08/Mens-Snowboard-Halfpipe.pdf"
}
```

### Result Entry
```json
{
  "rank": 1,
  "name": "JAMES Scotty",
  "is_medalist": true
}
```

## Technical Details

- **API**: WordPress REST API at `/en/wp-json/wp/v2/`
- **Categories**: Results are in category 17, with year subcategories (553=2024, 554=2025, 555=2026)
- **Content**: Athlete rankings are stored as ordered lists in post content
- **FIS Links**: Official detailed results available as PDF downloads

## Notes

- Results are parsed from HTML ordered lists where rank position corresponds to list position
- Top 3 athletes (podium) are marked with `<strong>` tags in the HTML
- FIS PDF links provide official detailed judging and scoring data
- Historical data availability depends on event year