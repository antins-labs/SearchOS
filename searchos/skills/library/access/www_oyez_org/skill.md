# Oyez.org Supreme Court Case Database Access Skill

## Overview

This skill provides programmatic access to the **Oyez Project** database, a comprehensive archive of U.S. Supreme Court cases. Oyez maintains detailed records including case metadata, oral argument audio, written opinions, and justice voting records.

## Discovered API

The Oyez website is a React-based SPA that fetches data from a REST API at:
- **API Base URL**: `https://api.oyez.org`
- **Case Endpoint**: `/cases/{term}/{docket}?labels=true`
- **Term List Endpoint**: `/cases/{term}?labels=true&page={n}`

The `labels=true` parameter expands related entities (parties, courts, advocates) inline.

## Functions

### `get_case`

Retrieve detailed information about a specific Supreme Court case.

**Parameters:**
- `term` (required): Court term year (e.g., "2024", "2023")
- `docket` (required): Docket number (e.g., "23-1239")

**Returns:**
- Case name, citation, parties
- Timeline (granted, argued, decided dates)
- Facts of the case, question presented, conclusion
- Advocates (attorneys arguing the case)
- Written opinions (majority, concurring, dissenting)
- Oral argument audio links
- Decision votes by justice

**Example:**
```python
result = await execute({
    "function": "get_case",
    "term": "2024",
    "docket": "23-1239"
})
# Returns: Barnes v. Felix details including conclusion about Fourth Amendment excessive force
```

### `get_cases_by_term`

Get a paginated list of all cases for a specific court term.

**Parameters:**
- `term` (required): Court term year
- `page` (optional): Page number (default 0, 30 cases per page)

**Returns:**
- List of case summaries (name, docket, term, citation, timeline)

**Example:**
```python
result = await execute({
    "function": "get_cases_by_term",
    "term": "2023"
})
# Returns all cases from October Term 2023
```

### `search_cases`

Search for cases by name or docket number across recent terms.

**Parameters:**
- `query` (required): Search string (case name or docket number)
- `max_terms` (optional): Number of recent terms to search (default 5)

**Returns:**
- Matching cases (limited to 50 results)

**Example:**
```python
result = await execute({
    "function": "search_cases",
    "query": "Harvard"
})
# Returns: Students for Fair Admissions v. Harvard and related cases
```

## Data Structure

### Case Summary
```json
{
  "id": 63710,
  "name": "Barnes v. Felix",
  "docket_number": "23-1239",
  "term": "2024",
  "citation": "605 U.S. ___ (2025)",
  "first_party": "Janice Hughes Barnes",
  "second_party": "Roberto Felix, Jr.",
  "timeline": [
    {"event": "Granted", "date": "2024-10-04"},
    {"event": "Argued", "date": "2025-01-22"},
    {"event": "Decided", "date": "2025-05-14"}
  ],
  "lower_court": "United States Court of Appeals for the Fifth Circuit"
}
```

### Case Detail (Additional Fields)
```json
{
  "facts_of_the_case": "On April 28, 2016, Officer Roberto Felix Jr...",
  "question": "Should courts apply the \"moment of the threat\" doctrine...",
  "conclusion": "An excessive force claim under the Fourth Amendment...",
  "advocates": [
    {"name": "Nathaniel A.G. Zelinsky", "role": "for the Petitioner"},
    {"name": "Zoe A. Jacoby", "role": "for the United States, as amicus curiae"}
  ],
  "written_opinions": [
    {"type": "Opinion of the Court", "author": "Elena Kagan"},
    {"type": "Concurring opinion", "author": "Brett M. Kavanaugh"}
  ],
  "decisions": [{
    "description": "Vacated and remanded...",
    "votes": [
      {"justice": "John G. Roberts, Jr.", "vote": "majority"},
      {"justice": "Clarence Thomas", "vote": "majority"}
    ]
  }]
}
```

## Content Processing

- HTML tags are stripped from `facts_of_the_case`, `question`, and `conclusion` fields
- Timestamps are converted from Unix epoch to ISO date strings (YYYY-MM-DD)
- Justice voting records include justice name and vote type
- Citations are formatted as `{volume} U.S. {page} ({year})`

## API Quirks

1. **List vs Single Response**: Some case endpoints return a list instead of a single object (particularly older cases). The skill handles this automatically.

2. **Timeline Events**: Not all cases have all timeline events. Pending cases only show "Granted" and possibly "Argued".

3. **Decisions Field**: The `decisions` field is `null` for cases not yet decided.

4. **Page Size**: Term listings return 30 cases per page.

## Use Cases

- Research Supreme Court jurisprudence
- Track case status and timeline
- Access opinion authorship and voting patterns
- Find oral argument audio for educational use
- Analyze court trends by term

## Attribution

Data sourced from the [Oyez Project](https://www.oyez.org), a free law project from Cornell's Legal Information Institute (LII), Justia, and Chicago-Kent College of Law.