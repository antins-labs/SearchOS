# La Biennale di Venezia Film Festival Extractor

This skill extracts structured film festival data from the official Venice Film Festival (La Biennale di Venezia) website. It can retrieve lineup sections, film listings within each section, and detailed information about individual films.

## Capabilities

- **Get Festival Lineup**: Retrieve all sections for a given year (Venezia Competition, Orizzonti, Out of Competition, Venice Classics, etc.)
- **Get Section Films**: List all films in a specific section with basic details (title, director, cast, country, duration)
- **Get Film Details**: Extract comprehensive film information including full cast, crew, production details, and synopsis
- **Search Films**: Search for films across all sections of a given festival year

## Supported Years

The extractor works with archived festival editions. Tested years include:
- 2019 (76th Venice International Film Festival)
- Other years should work as the website structure appears consistent

## Functions

### get_lineup

Get all sections/categories for a specific festival year.

**Parameters:**
- `function`: "get_lineup"
- `year`: Festival year (required)

**Example:**
```json
{
  "function": "get_lineup",
  "year": "2019"
}
```

**Returns:**
```json
{
  "success": true,
  "title": "Biennale Cinema 2019 | Lineup",
  "year": "2019",
  "sections": [
    {
      "title": "Venezia 76 Competition",
      "url": "https://www.labiennale.org/en/cinema/2019/venezia-76-competition",
      "path": "/en/cinema/2019/venezia-76-competition",
      "description": "An international competition comprising a maximum of 20 feature-length films..."
    },
    {
      "title": "Out of Competition",
      "url": "https://www.labiennale.org/en/cinema/2019/out-competition",
      "path": "/en/cinema/2019/out-competition",
      "description": "Works of established authors, documentaries and films..."
    }
  ]
}
```

### get_section

Retrieve all films in a specific festival section.

**Parameters:**
- `function`: "get_section"
- `url`: Full URL to the section page (optional if section_path + year provided)
- `section_path`: Section path name (optional)
- `year`: Festival year (optional, default: 2019)

**Example 1 - Using full URL:**
```json
{
  "function": "get_section",
  "url": "https://www.labiennale.org/en/cinema/2019/venezia-76-competition"
}
```

**Example 2 - Using path and year:**
```json
{
  "function": "get_section",
  "section_path": "venezia-76-competition",
  "year": "2019"
}
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.labiennale.org/en/cinema/2019/venezia-76-competition",
  "title": "Biennale Cinema 2019 | Venezia 76 Competition",
  "section": "Venezia 76 Competition",
  "year": "2019",
  "films": [
    {
      "title": "Joker",
      "director": "Todd Phillips",
      "main_cast": "Joaquin Phoenix, Robert De Niro",
      "country": "USA",
      "duration": "122'",
      "url": "https://www.labiennale.org/en/cinema/2019/venezia-76-competition/joker",
      "thumbnail": "https://static.labiennale.org/files/styles/square_thumb/public/cinema/2019/..."
    }
  ]
}
```

### get_film

Get detailed information about a specific film.

**Parameters:**
- `function`: "get_film"
- `url`: Full URL to the film page (required)

**Example:**
```json
{
  "function": "get_film",
  "url": "https://www.labiennale.org/en/cinema/2019/venezia-76-competition/ad-astra"
}
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.labiennale.org/en/cinema/2019/venezia-76-competition/ad-astra",
  "title": "Ad astra",
  "section": "Venezia 76 Competition",
  "year": "2019",
  "director": "James Gray",
  "production": "Plan B (Brad Pitt, Jeremy Kleiner, Dede Gardner), Keep Your Head Productions...",
  "running_time": "124'",
  "language": "English",
  "country": "USA",
  "main_cast": "Brad Pitt, Tommy Lee Jones, Ruth Negga, Liv Tyler, Donald Sutherland",
  "screenplay": "James Gray, Ethan Gross",
  "cinematographer": "Hoyte Van Hoytema",
  "editor": "John Axelrad, Ace and Lee Haugen",
  "production_designer": "Kevin Thompson",
  "costume_designer": "Albert Wolsky",
  "music": "Max Richter. Additional music by Lorne Balfe",
  "sound": "Mark Ulano",
  "visual_effects": "Scott R. Fisher, Allen Harris",
  "synopsis": "..."
}
```

### search_films

Search for films by title or director across all sections of a festival year.

**Parameters:**
- `function`: "search_films"
- `query`: Search term (film title or director name)
- `year`: Festival year (optional, default: 2019)

**Example:**
```json
{
  "function": "search_films",
  "query": "Joker",
  "year": "2019"
}
```

**Returns:**
```json
{
  "success": true,
  "query": "Joker",
  "year": "2019",
  "total_results": 1,
  "films": [
    {
      "title": "Joker",
      "director": "Todd Phillips",
      "main_cast": "Joaquin Phoenix, Robert De Niro",
      "match_score": 100,
      "section_title": "Venezia 76 Competition",
      "url": "https://www.labiennale.org/en/cinema/2019/venezia-76-competition/joker"
    }
  ]
}
```

## Section Paths

Common section paths used with `get_section`:

- `venezia-76-competition` - Main competition (name varies by year, e.g., venezia-77-competition)
- `out-competition` - Out of Competition
- `orizzonti` - Orizzonti competition
- `venice-classics` - Venice Classics
- `sconfini` - Sconfini
- `biennale-college-cinema` - Biennale College Cinema
- `venice-virtual-reality` - Venice Virtual Reality

## Notes

- The extractor parses HTML pages from the official La Biennale website
- Film details availability varies by year and section
- Some films may have limited information in the listing view; use `get_film` for complete details
- The website uses rate limiting; avoid making too many rapid requests
- Film URLs are stable and can be bookmarked for later reference

## Error Handling

All functions return a structured response with:
- `success`: Boolean indicating if the operation succeeded
- `error`: Error message (if success is false)
- `error_type`: "validation", "network", or "parse"

Common errors:
- Missing required parameters
- Invalid year or URL
- Network timeout or connection failure
- Page structure not recognized (rare, indicates website changes)