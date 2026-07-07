# Justia Supreme Court Opinions Access Skill

Fetches U.S. Supreme Court opinions from Justia's comprehensive database at `supreme.justia.com`.

## Features

- **Year Index**: Get all cases from a specific term year (e.g., 2024, 2025)
- **Volume Index**: Get all cases from a U.S. Reports volume (e.g., 605, 600)
- **Case Details**: Get detailed information about a specific case including:
  - Case title and citation
  - Docket number and important dates (granted, argued, decided)
  - Opinion text snippets
  - Official PDF download links
  - Related materials (briefs, filings)

## Usage Examples

### Get cases from a year

```json
{
  "function": "get_year_cases",
  "year": 2025
}
```

Returns all Supreme Court opinions from 2025 with:
- Case titles and docket numbers
- Decision dates
- Whether Justia summaries/annotations are available

### Get a specific case

```json
{
  "function": "get_case",
  "volume": "605",
  "docket": "24-394"
}
```

Returns detailed case information for *OK Charter School Board v. Drummond*:
- Full citation (605 U.S. ___ (2025))
- Important dates
- Opinion content (majority, concurrences, dissents)
- PDF links to official opinions

### Get cases from a volume

```json
{
  "function": "get_volume_cases",
  "volume": "600"
}
```

Returns all cases in U.S. Reports volume 600.

## Data Structure

### Year Index Response

```json
{
  "success": true,
  "year": 2025,
  "url": "https://supreme.justia.com/cases/federal/us/year/2025.html",
  "total": 62,
  "page_title": "Opinions from 2025",
  "cases": [
    {
      "volume": "607",
      "docket": "25-180",
      "title": "Doe v. Dynamic Physical Therapy, LLC",
      "date": "December 8, 2025",
      "has_justia_summary": true,
      "has_justia_annotation": true,
      "url": "https://supreme.justia.com/cases/federal/us/607/25-180/"
    }
  ]
}
```

### Case Detail Response

```json
{
  "success": true,
  "volume": "605",
  "docket": "24-394",
  "url": "https://supreme.justia.com/cases/federal/us/605/24-394/",
  "title": "OK Charter School Board v. Drummond, 605 U.S. ___ (2025)",
  "citation": {
    "volume": "605",
    "page": "___",
    "year": "2025",
    "full": "605 U.S. ___ (2025)"
  },
  "docket_number": "24-394",
  "granted_date": "January 24, 2025",
  "argued_date": "April 30, 2025",
  "decided_date": "May 22, 2025",
  "opinions": [
    {
      "type": "per_curiam",
      "tab_id": "tab-opinion-5054092",
      "length": 876,
      "snippet": "The judgment is affirmed by an equally divided Court..."
    }
  ],
  "official_pdf": "https://www.supremecourt.gov/opinions/24pdf/24-394_9p6b.pdf"
}
```

## Opinion Types

The skill identifies the following opinion types:
- `majority` - Opinion of the Court
- `per_curiam` - Per Curiam opinion
- `concurrence` - Concurring opinion
- `dissent` - Dissenting opinion
- `unknown` - Could not determine type

## Notes

- The site is protected by Cloudflare, so this skill uses `curl_cffi` with Safari impersonation to access the pages.
- The `docket` parameter format is typically `YY-NNN` (e.g., "24-394", "23-1122").
- U.S. Reports volumes are sequential (currently around 605-607 for 2024-2025 terms).
- Year indices group cases by the Court's term year (October to June/July).
- PDF links point to the official Supreme Court website (supremecourt.gov).

## Dependencies

- `curl_cffi` - Required for Cloudflare bypass
- `beautifulsoup4` - HTML parsing