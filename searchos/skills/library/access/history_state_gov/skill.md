# History.State.Gov Access Skill

## Overview

This skill provides structured access to the U.S. State Department Office of the Historian website (history.state.gov). The site contains comprehensive biographical records of U.S. Secretaries of State, Principal Officers, and Chiefs of Mission dating back to 1778.

## Functions

### get_person

Retrieve detailed biography for a specific person.

**Parameters:**
- `slug` (optional): The person's URL slug (e.g., 'jefferson-thomas', 'tillerson-rex-w')
- `url` (optional): Full URL to the person page (alternative to slug)

**Returns:**
```json
{
  "success": true,
  "url": "https://history.state.gov/departmenthistory/people/jefferson-thomas",
  "slug": "jefferson-thomas",
  "name": "Thomas Jefferson",
  "full_title": "Biographies of the Secretaries of State:Thomas Jefferson (1743–1826)",
  "birth_year": "1743",
  "death_year": "1826",
  "state_of_residence": "Virginia",
  "position": "Minister Plenipotentiary (France)",
  "positions": [
    {
      "title": "Minister Plenipotentiary (France)",
      "position_href": "/departmenthistory/people/chiefsofmission/france",
      "appointed": "March 10, 1785",
      "presentation_of_credentials": "May 17, 1785",
      "termination_of_mission": "Left post on September 26, 1789",
      "notes": "Recommissioned on October 12, 1787."
    },
    {
      "title": "Secretary of State",
      "position_href": "/departmenthistory/people/principalofficers/secretary",
      "appointed": "September 26, 1789",
      "entry_on_duty": "March 22, 1790",
      "termination_of_appointment": "December 31, 1793"
    }
  ],
  "introduction": "Thomas Jefferson served as the first Secretary of State...",
  "sources": "This text was adapted from..."
}
```

### search_people

Search for people by name across the entire database.

**Parameters:**
- `query` (required): Search query (person's name or partial name)

**Returns:**
```json
{
  "success": true,
  "query": "kissinger",
  "count": 10,
  "results": [
    {
      "title": "Henry A. (Heinz Alfred) Kissinger",
      "url": "https://history.state.gov/departmenthistory/people/kissinger-henry-a",
      "slug": "kissinger-henry-a",
      "type": "person"
    }
  ]
}
```

### list_secretaries

List all U.S. Secretaries of State.

**Returns:**
```json
{
  "success": true,
  "title": "Biographies of the Secretaries of State",
  "count": 70,
  "people": [
    {
      "name": "Thomas Jefferson",
      "url": "https://history.state.gov/departmenthistory/people/jefferson-thomas",
      "slug": "jefferson-thomas"
    }
  ]
}
```

### list_by_name

List alphabetical index for browsing Principal Officers and Chiefs of Mission by last name. Use `get_by_name_letter` to retrieve people for a specific letter.

**Returns:**
```json
{
  "success": true,
  "title": "Principal Officers and Chiefs of Mission Alphabetical Listing",
  "type": "alphabetical_index",
  "count": 26,
  "letters": [
    {"letter": "A", "url": "https://history.state.gov/departmenthistory/people/by-name/a"},
    {"letter": "B", "url": "https://history.state.gov/departmenthistory/people/by-name/b"},
    ...
  ],
  "description": "Use get_by_name_letter(letter='a') to get people for a specific letter"
}
```

### get_by_name_letter

Get all people whose last name starts with a specific letter.

**Parameters:**
- `letter` (required): Single letter (a-z)

**Returns:**
```json
{
  "success": true,
  "letter": "a",
  "title": "Principal Officers and Chiefs of Mission, by Name: A",
  "count": 134,
  "people": [
    {
      "name": "David Laurence Aaron (1938–)",
      "url": "https://history.state.gov/departmenthistory/people/aaron-david-laurence",
      "slug": "aaron-david-laurence"
    }
  ]
}
```

### list_by_year

List year index for browsing by appointment year. Use `get_by_year` to retrieve people for a specific year.

**Returns:**
```json
{
  "success": true,
  "title": "Principal Officers and Chiefs of Mission Chronological Listing",
  "type": "year_index",
  "count": 248,
  "year_range": "1778-2025",
  "years": [
    {"year": "1778", "url": "https://history.state.gov/departmenthistory/people/by-year/1778"},
    {"year": "1779", "url": "https://history.state.gov/departmenthistory/people/by-year/1779"},
    ...
  ]
}
```

### get_by_year

Get all people appointed in a specific year.

**Parameters:**
- `year` (required): Four-digit year (e.g., 2020)

**Returns:**
```json
{
  "success": true,
  "year": "2020",
  "title": "Principal Officers and Chiefs of Mission, by Year: 2020",
  "count": 56,
  "people": [
    {
      "name": "Luis E. Arreaga-Rodas (1952–)",
      "url": "https://history.state.gov/departmenthistory/people/arreaga-rodas-luis-e",
      "slug": "arreaga-rodas-luis-e"
    }
  ]
}
```

## Data Structure

Each person record includes:

- **Basic Info**: Name, birth year, death year (if deceased)
- **State of Residence**: Home state at time of appointment
- **Appointment Type**: Career appointee, Non-career appointee, Career Member
- **Positions**: Array of positions held with:
  - Title (e.g., "Secretary of State", "Ambassador to France")
  - Appointment date
  - Entry on duty date
  - Presentation of credentials date (for ambassadors)
  - Termination date
  - Notes (if any, such as recommissioning)
- **Introduction**: Biographical summary
- **Sources**: Citation information

## Examples

```python
# Get a specific person
result = await execute({
    "function": "get_person",
    "slug": "tillerson-rex-w"
})

# Search for someone
result = await execute({
    "function": "search_people",
    "query": "kissinger"
})

# List all Secretaries of State
result = await execute({
    "function": "list_secretaries"
})

# Browse alphabetically
result = await execute({
    "function": "get_by_name_letter",
    "letter": "a"
})

# Browse by year
result = await execute({
    "function": "get_by_year",
    "year": 2020
})
```

## Notes

- The site uses static HTML pages, no API is available
- All data is scraped from HTML using BeautifulSoup
- Person slugs follow the pattern: `lastname-firstname` (e.g., `clinton-hillary-rodham`)
- Historical records span from 1778 to present
- The database includes:
  - Secretaries of State
  - Deputy Secretaries
  - Under Secretaries
  - Assistant Secretaries
  - Chiefs of Mission (Ambassadors)
- Living people have birth year only (e.g., "1952–")
- Deceased people have both years (e.g., "1743–1826")

## Rate Limiting

The skill implements conservative rate limiting:
- 2 requests per second
- 60 requests per minute

This ensures we don't overwhelm the government server.