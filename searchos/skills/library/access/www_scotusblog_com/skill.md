# SCOTUSblog Access Skill

This skill provides programmatic access to Supreme Court case data from SCOTUSblog (www.scotusblog.com), sourced from their publicly accessible Sanity CMS API.

## Overview

SCOTUSblog is a leading resource for Supreme Court news, analysis, and case tracking. This skill enables you to:

- List all Supreme Court terms (October Term 2007 onwards)
- Get cases for a specific term with filtering by status
- Retrieve detailed case information including holdings, judgments, and proceedings
- Search cases by title or docket number
- Get statistics about a term (cases granted, argued, decided, pending)
- List opinion authors (justices) and their authored opinions
- Track recent decisions and upcoming arguments

## Data Source

Data is fetched directly from SCOTUSblog's Sanity CMS API at:
```
https://pito4za5.api.sanity.io/v1/data/query/production
```

This API is publicly accessible and provides structured data for all Supreme Court cases tracked by SCOTUSblog.

## Functions

### list_terms

Lists all Supreme Court terms with case counts.

```json
{"function": "list_terms"}
```

**Returns:**
- `terms`: Array of term objects with title, slug, dates, and case count

### get_term_cases

Get all cases for a specific term.

```json
{"function": "get_term_cases", "term": "ot2024", "limit": 50}
```

**Parameters:**
- `term` (required): Term slug (e.g., "ot2024")
- `status` (optional): Filter by status ("decided", "pending", "granted", "denied")
- `limit` (optional): Max results (default: 100)
- `offset` (optional): Pagination offset (default: 0)

**Returns:**
- `cases`: Array of case objects
- `total`: Total count matching the query

### get_term_stats

Get statistics for a specific term.

```json
{"function": "get_term_stats", "term": "ot2024"}
```

**Returns:**
- `term`: Term details (title, slug, dates)
- `statistics`: Counts by status (total, decided, pending, granted, denied, argued)

### get_case

Get detailed information about a specific case.

```json
{"function": "get_case", "slug": "dewberry-group-inc-v-dewberry-engineers-inc"}
```

Or by docket number:
```json
{"function": "get_case", "docket_number": "23-900"}
```

**Returns:**
- `case`: Full case details including:
  - `title`, `slug`, `docket_number`, `status`
  - `date_argued`, `date_decided`, `vote`
  - `opinion_author`, `result`, `result_details`
  - `holding`, `judgment`, `issue_area` (extracted text)
  - `proceedings`: Timeline of court actions
  - `supreme_court_url`, `opinion_url`

### search_cases

Search for cases by title or docket number.

```json
{"function": "search_cases", "query": "trademark"}
```

**Returns:**
- `cases`: Array of matching cases
- `total`: Count of results

### list_opinion_authors

List all justices who have authored opinions.

```json
{"function": "list_opinion_authors"}
```

**Returns:**
- `authors`: Array of justice names with case counts

### get_cases_by_author

Get all cases authored by a specific justice.

```json
{"function": "get_cases_by_author", "author": "Kagan"}
```

**Returns:**
- `cases`: Array of cases authored by the justice
- `total`: Count of cases

### get_recent_decisions

Get the most recent Supreme Court decisions.

```json
{"function": "get_recent_decisions", "limit": 10, "term": "ot2024"}
```

**Parameters:**
- `limit` (optional): Max results (default: 10)
- `term` (optional): Filter to specific term

**Returns:**
- `cases`: Array of recently decided cases

### get_upcoming_arguments

Get pending cases awaiting decisions.

```json
{"function": "get_upcoming_arguments", "term": "ot2025"}
```

**Returns:**
- `cases`: Array of pending cases

## Data Fields

### Case Status Values
- `decided`: Case has been decided
- `pending`: Case has been argued, awaiting decision
- `granted`: Cert petition granted
- `denied`: Cert petition denied

### Proceeding Colors
The `color` field in proceedings indicates the type of filing:
- `white`: Routine filings
- `cream`: Amicus briefs
- `orange`: Opposition briefs
- `tan`: Reply briefs
- `blue`: Merits briefs (petitioner)
- `red`: Merits briefs (respondent)

## Examples

### Get all decided cases from OT2024

```json
{
  "function": "get_term_cases",
  "term": "ot2024",
  "status": "decided",
  "limit": 20
}
```

### Find a case by docket number

```json
{
  "function": "get_case",
  "docket_number": "23-900"
}
```

### Search for cases about a topic

```json
{
  "function": "search_cases",
  "query": "voting rights"
}
```

### Get recent decisions from October Term 2025

```json
{
  "function": "get_recent_decisions",
  "term": "ot2025",
  "limit": 5
}
```

## Rate Limits

The Sanity CMS API is publicly accessible with no documented rate limits. However, please use reasonable request rates and avoid excessive querying.

## Coverage

- Supreme Court terms from October Term 2007 to present
- Case data includes docket information, proceedings, opinions, and analysis
- Data is updated regularly by SCOTUSblog editors