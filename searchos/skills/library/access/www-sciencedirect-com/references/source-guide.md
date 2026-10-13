# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# ScienceDirect Article Access Skill

This skill retrieves academic article metadata from ScienceDirect/Elsevier publications using open APIs. Since ScienceDirect.com blocks direct web scraping with 403 errors, this skill uses alternative open APIs that provide access to the same academic content.

## Features

### Get Article Metadata
Retrieve comprehensive metadata for a specific article using its DOI or PII:

```json
{
  "function": "get_article",
  "doi": "10.1016/j.tust.2021.104281"
}
```

Or using PII:
```json
{
  "function": "get_article",
  "pii": "S0886779821004727"
}
```

**Returns:**
- Article title, DOI, PII, year
- Authors with affiliations and ORCID IDs
- Abstract (when available)
- Journal/venue information
- Citation count
- Open access status and PDF URL (if available)
- Keywords and topics
- Sustainable Development Goals (if applicable)

### Search Articles
Search for articles by keywords:

```json
{
  "function": "search_articles",
  "query": "tunnelling Hong Kong",
  "limit": 10
}
```

**Parameters:**
- `query`: Search terms
- `limit`: Maximum results (default: 10, max: 50)
- `source`: API to use - "openalex" (default), "crossref", or "all"

## Data Sources

This skill aggregates data from multiple open academic APIs:

1. **OpenAlex** (primary)
   - Comprehensive metadata
   - Abstracts (reconstructed from inverted index)
   - Citations and impact metrics
   - Author affiliations
   - Topics and keywords

2. **Semantic Scholar**
   - Citation counts
   - Open access PDF links
   - Author information

3. **CrossRef**
   - Bibliographic data
   - References
   - Publisher information

4. **Elsevier API**
   - Publisher-specific metadata
   - PII/EID identifiers
   - Open access status

## Response Structure

### Get Article Response

```json
{
  "success": true,
  "doi": "10.1016/j.tust.2021.104281",
  "pii": "S0886779821004727",
  "sources": ["openalex", "semantic_scholar", "crossref", "elsevier"],
  "article": {
    "title": "Shatin to Central Link cross-harbour railway tunnel in Hong Kong",
    "doi": "10.1016/j.tust.2021.104281",
    "year": 2022,
    "authors": [
      {"name": "Fumihiro Aikawa", "orcid": "..."},
      ...
    ],
    "abstract": "...",
    "journal": "Tunnelling and Underground Space Technology",
    "citation_count": 12,
    "is_open_access": true,
    "open_access_pdf_url": "https://..."
  },
  "data": {
    "openalex": {...},
    "semantic_scholar": {...},
    "crossref": {...},
    "elsevier": {...}
  }
}
```

### Search Articles Response

```json
{
  "success": true,
  "query": "tunnelling Hong Kong",
  "total_returned": 10,
  "articles": [
    {
      "title": "...",
      "doi": "...",
      "year": 2022,
      "authors": ["...", "..."],
      "venue": "...",
      "open_access": true,
      "cited_by_count": 15,
      "source": "openalex"
    },
    ...
  ]
}
```

## Limitations

- Full text is not available through these APIs (only metadata and abstracts)
- Some articles may not have abstracts available
- Open access PDF availability varies by article
- The Elsevier API provides limited data without an API key

## Use Cases

1. **Literature Review**: Search and collect metadata for academic papers
2. **Citation Analysis**: Get citation counts and track paper impact
3. **Author Research**: Find author affiliations and ORCID IDs
4. **Open Access Discovery**: Find freely available PDF versions
5. **Bibliographic Management**: Export citation metadata
