# MGM China Holdings - Investor Reports Access Skill

This skill fetches annual and interim financial reports from MGM China Holdings Limited's investor relations website.

## Source

- **Website**: https://en.mgmchinaholdings.com
- **Reports Page**: https://en.mgmchinaholdings.com/IR-Annual-and-Interim-Reports

## Available Data

The skill provides access to:
- **Annual Reports** (年度报告): Complete annual financial statements and disclosures
- **Interim Reports** (中期报告): Half-year financial reports

Data available from 2011 to present (15+ years of reports).

## Functions

### list_all
Lists all available reports (both annual and interim).

```python
result = await execute({'function': 'list_all'})
```

Returns a list of all reports sorted by year (newest first), with each entry containing:
- `title`: Report title
- `year`: Publication year
- `type`: "annual" or "interim"
- `size`: File size
- `url`: Download URL

### list_annual / list_interim
Filters reports by type.

```python
# Get all annual reports
result = await execute({'function': 'list_annual'})

# Get all interim reports  
result = await execute({'function': 'list_interim'})
```

### get_by_year
Retrieves reports for a specific year.

```python
result = await execute({'function': 'get_by_year', 'year': 2024})
```

Returns both annual and interim reports for the specified year.

### get_latest
Gets the most recent report of a specified type.

```python
# Get latest annual report (default)
result = await execute({'function': 'get_latest'})

# Get latest interim report
result = await execute({'function': 'get_latest', 'report_type': 'interim'})
```

### resolve_url
Resolves a PDF URL to its final CDN location.

```python
result = await execute({
    'function': 'resolve_url',
    'url': 'https://en.mgmchinaholdings.com/image/e02282_2025AR.pdf'
})
```

Returns:
- `original_url`: The input URL
- `final_url`: The resolved CDN URL (e.g., filecache.investorroom.com)
- `content_type`: MIME type (application/pdf)
- `content_length`: File size in bytes

## Response Format

All responses include:
```json
{
  "success": true/false,
  "count": <number of results>,
  "reports": [...],  // for list functions
  "report": {...},   // for get_latest
  "source": "https://en.mgmchinaholdings.com/IR-Annual-and-Interim-Reports",
  "error": null or error message
}
```

## Technical Notes

- The website serves static HTML; no JavaScript rendering required
- PDF URLs redirect (302) to a CDN at `filecache.investorroom.com`
- Reports are typically 2-40 MB in size
- The site uses a custom "webdriver" CMS with specific CSS classes for attachments