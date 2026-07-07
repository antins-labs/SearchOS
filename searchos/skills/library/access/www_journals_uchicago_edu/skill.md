# UChicago Journals Access Skill

Access metadata for University of Chicago Press journal articles and table of contents.

## Overview

This skill provides access to UChicago Press journals through the Crossref API, bypassing Cloudflare protection on the main website. It can retrieve article metadata, references, and table of contents for journals like:

- American Journal of Sociology (ajs)
- Journal of Political Economy (jpe)
- Journal of Law and Economics (jols)
- Journal of Labor Economics (jole)
- The American Naturalist (an)
- Current Anthropology (ca)
- International Journal of American Linguistics (ijal)
- American Journal of Archaeology (ajsarch)
- The Journal of Politics (jop)
- And more...

## Why Crossref?

The www.journals.uchicago.edu website uses Cloudflare Turnstile security verification that blocks automated access. All direct HTTP requests return 403 errors with a JavaScript challenge. This skill works around this limitation by using the Crossref API, which provides comprehensive bibliographic metadata for all DOI-registered publications, including:

- Article titles and authors
- Journal names, volumes, and issues
- Page numbers and publication dates
- DOI and URL links
- References cited by articles
- Citation counts

## Functions

### list_journals
List all supported UChicago Press journals with their codes and ISSNs.

```
{
  "function": "list_journals"
}
```

### get_article_metadata
Get complete metadata for a specific article by DOI.

```
{
  "function": "get_article_metadata",
  "doi": "10.1086/739568"
}
```

Returns: title, authors, journal, volume, issue, pages, publication date, references, citation count, and more.

### get_toc_current
Get the current (most recent) issue's table of contents for a journal.

```
{
  "function": "get_toc_current",
  "journal_code": "ajs",
  "limit": 50
}
```

Returns: journal info, current issue details, and list of articles with full metadata.

### get_toc_issue
Get the table of contents for a specific volume and issue.

```
{
  "function": "get_toc_issue",
  "journal_code": "ajs",
  "volume": "131",
  "issue": "4"
}
```

Returns: issue details and list of articles in publication order.

### get_references
Get the references cited by an article.

```
{
  "function": "get_references",
  "doi": "10.1086/739568",
  "limit": 100
}
```

Returns: list of references with DOIs, years, titles, and authors where available.

### search_articles
Search for articles in a journal (limited to recent works, with optional filtering).

```
{
  "function": "search_articles",
  "journal_code": "ajs",
  "query": "immigration",
  "limit": 20
}
```

Returns: list of matching articles with full metadata.

## Journal Codes

Common journal codes (use `list_journals` for complete list):

| Code | Journal Name |
|------|--------------|
| ajs | American Journal of Sociology |
| jpe | Journal of Political Economy |
| jols | Journal of Law and Economics |
| jole | Journal of Labor Economics |
| an | The American Naturalist |
| ca | Current Anthropology |
| ijal | International Journal of American Linguistics |
| ajsarch | American Journal of Archaeology |
| jop | The Journal of Politics |
| jacr | Journal of the Association for Consumer Research |

## Data Sources

- **Crossref API** (https://api.crossref.org) - Primary source for article metadata
- **DOI Prefix**: 10.1086 (University of Chicago Press)

## Limitations

1. **No Full Text**: This skill only provides bibliographic metadata, not article full text or abstracts
2. **Search Limitations**: Crossref search is limited; use query parameter to filter results locally
3. **Coverage**: Only articles with DOIs are available; very recent articles may not yet be indexed
4. **References**: Reference details vary; some references may only have DOIs or minimal information

## Example Usage

### Get article metadata
```python
result = await execute({
    "function": "get_article_metadata",
    "doi": "10.1086/739568"
})

# Returns:
{
  "success": true,
  "article": {
    "doi": "10.1086/739568",
    "title": "Red and Blue Immigrants: Political (Mis)Alignment...",
    "authors": [{"given": "Keitaro", "family": "Okura"}],
    "journal": "American Journal of Sociology",
    "volume": "131",
    "issue": "4",
    "page": "729-772",
    "published_date": [2026, 1, 1],
    "reference_count": 99,
    "is_referenced_by_count": 1,
    ...
  }
}
```

### Get current issue TOC
```python
result = await execute({
    "function": "get_toc_current",
    "journal_code": "ajs"
})

# Returns current issue with article list
```

### Get specific issue TOC
```python
result = await execute({
    "function": "get_toc_issue",
    "journal_code": "ajs",
    "volume": "131",
    "issue": "4"
})

# Returns Volume 131, Issue 4 article list
```

## Error Handling

All functions return a dictionary with:
- `success`: boolean indicating success/failure
- `error`: error message if success is false
- Additional data fields if success is true

Common errors:
- Unknown journal code: Check supported codes with `list_journals`
- DOI not found: Article may not be indexed in Crossref
- Missing parameters: Check required parameters for each function