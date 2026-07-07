# Springer Link Access Skill

Extract structured metadata from academic articles and journal issues on Springer Link (link.springer.com).

## Functions

### get_article

Extract comprehensive metadata for an academic article.

**Parameters:**
- `doi` (string, required if no URL): Article DOI, e.g., "10.1057/s41290-024-00210-2"
- `url` (string, required if no DOI): Full article URL

**Example:**
```python
result = await execute({
    "function": "get_article",
    "doi": "10.1057/s41290-024-00210-2"
})
```

**Returns:**
- `headline`: Article title
- `authors`: List of author objects with names, ORCID, affiliation
- `author_names`: Simplified list of author names
- `abstract`: Article abstract
- `journal`: Journal name
- `issn`: List of ISSNs
- `volume`, `issue`: Volume and issue numbers
- `page_start`, `page_end`: Page range
- `date_published`: Publication date
- `keywords`: Subject keywords
- `doi`: Digital Object Identifier
- `pdf_url`: Direct PDF link
- `publisher`: Publisher name

---

### get_issue

Get article listings from a specific journal issue.

**Parameters:**
- `journal_id` (string): Journal numeric ID, e.g., "41290"
- `volume` (string): Volume number
- `issue` (string): Issue number
- OR `url`: Full issue page URL

**Example:**
```python
result = await execute({
    "function": "get_issue",
    "journal_id": "41290",
    "volume": "12",
    "issue": "4"
})
```

**Returns:**
- `volume`, `issue`: Volume and issue numbers
- `issue_title`: Human-readable issue title
- `journal`: Journal name
- `article_count`: Number of articles found
- `articles`: List of article summaries with:
  - `title`, `doi`, `url`
  - `authors`: List of author names
  - `article_type`: Article type if detected
  - `open_access`: Boolean if open access

---

### list_issues

List available issues for a journal.

**Parameters:**
- `journal_id` (string): Journal numeric ID
- OR `url`: Full journal page URL

**Example:**
```python
result = await execute({
    "function": "list_issues",
    "journal_id": "41290"
})
```

**Returns:**
- `journal`: Journal name
- `issue_count`: Number of issues found
- `issues`: List of issue objects with:
  - `volume`, `issue`: Volume and issue numbers
  - `label`: Human-readable label
  - `url`: Issue page URL

## Data Sources

The skill extracts data from:
1. **JSON-LD**: Structured data in `<script type="application/ld+json">`
2. **Citation Meta Tags**: Highwire Press compatible meta tags (e.g., `citation_title`, `citation_author`)
3. **HTML Structure**: Semantic markup for article listings

## Error Handling

All functions return structured error responses:
- `success`: Boolean indicating success/failure
- `error`: Human-readable error message
- `error_code`: Machine-readable error code:
  - `NOT_FOUND`: Resource not found (404)
  - `HTTP_ERROR`: Other HTTP errors
  - `TIMEOUT`: Request timed out
  - `NETWORK_ERROR`: Connection failures
  - `PARSE_ERROR`: Failed to extract data
  - `UNEXPECTED_ERROR`: Other errors

## Notes

- Uses direct HTTP requests with HTML parsing (no API required)
- Respects robots.txt and rate limiting considerations
- Works with most Springer Nature journals on link.springer.com
- Does not access paywalled content beyond metadata

## Examples

### Get article with known DOI
```python
from executor import execute

result = await execute({
    "function": "get_article",
    "doi": "10.1057/s41290-024-00215-x"
})

if result["success"]:
    article = result["data"]
    print(f"Title: {article['headline']}")
    print(f"Authors: {', '.join(article['author_names'])}")
    print(f"Abstract: {article['abstract'][:200]}...")
```

### Browse journal issues
```python
# Get issues for American Journal of Cultural Sociology (journal ID: 41290)
issues_result = await execute({
    "function": "list_issues",
    "journal_id": "41290"
})

# Get articles from a specific issue
issue_result = await execute({
    "function": "get_issue",
    "journal_id": "41290",
    "volume": "12",
    "issue": "4"
})

# Then get full metadata for each article
for article in issue_result["data"]["articles"]:
    full_article = await execute({
        "function": "get_article",
        "doi": article["doi"]
    })
```

### Batch article extraction
```python
# From an issue page
issue = await execute({
    "function": "get_issue",
    "url": "https://link.springer.com/journal/41290/volumes-and-issues/12-4"
})

# Extract all articles
articles = []
for article_summary in issue["data"]["articles"]:
    article = await execute({
        "function": "get_article",
        "doi": article_summary["doi"]
    })
    if article["success"]:
        articles.append(article["data"])
```

## Limitations

1. **Access**: Only metadata from publicly visible pages; full text may require subscription
2. **Coverage**: Works primarily with Springer Nature journals on link.springer.com
3. **Rate Limits**: Implement your own rate limiting for bulk operations
4. **Gabmling**: Some gateway pages may not parse correctly