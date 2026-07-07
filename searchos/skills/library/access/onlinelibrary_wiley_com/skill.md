# Wiley Online Library Access Skill

Access journal article metadata from Wiley Online Library using alternative API sources.

## Overview

The Wiley Online Library (onlinelibrary.wiley.com) is protected by Cloudflare and returns 403 errors for automated access. This skill bypasses the protection by fetching article metadata from two public APIs that index Wiley content:

- **CrossRef API**: The official DOI registration agency's API, providing authoritative bibliographic metadata
- **Semantic Scholar API**: AI-powered research tool providing citations, abstracts, and open access information

## Features

- **Comprehensive Metadata**: Title, authors, abstract, journal, volume, issue, pages, publication dates
- **Citation Data**: Citation counts, reference counts
- **Open Access Info**: Open access PDF availability via Semantic Scholar
- **Multiple Input Formats**: Accepts DOI, Wiley URLs, or doi.org URLs
- **Batch Processing**: Fetch multiple articles in a single call
- **DOI Extraction**: Extract DOI from various URL formats

## Functions

### fetch_article

Fetch metadata for a single article by DOI or URL.

**Parameters:**
- `doi` (string): DOI identifier like "10.1111/ajes.12597"
- `url` (string): Wiley Online Library or doi.org URL (alternative to doi)

**Returns:**
```json
{
  "success": true,
  "data": {
    "doi": "10.1111/ajes.12597",
    "title": "Article Title",
    "authors": [{"name": "Author Name", "given": "Author", "family": "Name"}],
    "abstract": "Article abstract...",
    "journal": "Journal Name",
    "journal_short": "J. Short",
    "year": 2024,
    "volume": "84",
    "issue": "1",
    "pages": "135-152",
    "publisher": "Wiley",
    "citation_count": 3,
    "open_access": {"is_open_access": false, "pdf_url": null},
    "fields_of_study": [{"category": "Sociology", "source": "s2-fos-model"}],
    "urls": {
      "crossref": "https://doi.org/10.1111/ajes.12597",
      "semanticscholar": "https://www.semanticscholar.org/paper/..."
    },
    "sources": ["crossref", "semanticscholar"]
  }
}
```

### fetch_articles

Fetch metadata for multiple articles in batch.

**Parameters:**
- `dois` (array or string): List of DOIs, or comma/newline separated string

**Returns:**
```json
{
  "success": true,
  "articles": [...],
  "summary": {
    "total": 3,
    "successful": 3,
    "failed": 0
  }
}
```

### extract_doi

Extract DOI from a Wiley or doi.org URL.

**Parameters:**
- `url` (string): URL to extract DOI from

**Returns:**
```json
{
  "success": true,
  "doi": "10.1111/ajes.12597",
  "url": "https://onlinelibrary.wiley.com/doi/10.1111/ajes.12597"
}
```

## Example Usage

```python
# Single article by DOI
result = await execute({
    "function": "fetch_article",
    "doi": "10.1111/ajes.12597"
})

# Single article by URL
result = await execute({
    "function": "fetch_article",
    "url": "https://onlinelibrary.wiley.com/doi/abs/10.1111/ajes.12402"
})

# Multiple articles
result = await execute({
    "function": "fetch_articles",
    "dois": ["10.1111/ajes.12597", "10.1111/ajes.12402", "10.1111/ajes.12438"]
})

# Extract DOI from URL
result = await execute({
    "function": "extract_doi",
    "url": "https://onlinelibrary.wiley.com/doi/full/10.1111/ajes.12597"
})
```

## Supported URL Formats

- `https://onlinelibrary.wiley.com/doi/10.xxxx/yyy`
- `https://onlinelibrary.wiley.com/doi/abs/10.xxxx/yyy`
- `https://onlinelibrary.wiley.com/doi/full/10.xxxx/yyy`
- `https://onlinelibrary.wiley.com/doi/pdf/10.xxxx/yyy`
- `https://doi.org/10.xxxx/yyy`
- `http://doi.org/10.xxxx/yyy`

## Data Sources

### CrossRef
- Official DOI registration agency
- Provides: title, authors, journal, volume, issue, pages, dates, ISSN, license info
- Rate limit: Polite with User-Agent header

### Semantic Scholar
- AI-powered academic search engine
- Provides: abstract (clean text), citation count, open access PDF links, fields of study
- Rate limit: Public API, no authentication required

## Limitations

- Does not access full article text or PDFs (Wiley requires subscription)
- Abstract availability depends on publisher submission to CrossRef
- Some newly published articles may not yet be indexed by Semantic Scholar
- Direct Wiley website access is blocked by Cloudflare

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Failed to fetch metadata from any source",
  "details": ["CrossRef HTTP 404: ...", "Semantic Scholar: DOI not found"],
  "doi": "10.xxxx/invalid"
}
```

## Notes

- The skill prefers CrossRef for bibliographic data (authors, journal info) as it's authoritative
- Semantic Scholar enhances with citation counts and clean abstracts
- Both APIs are free and don't require authentication
- Results include which sources were successfully queried