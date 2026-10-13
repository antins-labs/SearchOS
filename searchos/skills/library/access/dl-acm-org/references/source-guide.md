# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# ACM Digital Library Access Skill

This skill retrieves bibliographic metadata for ACM publications. Since the main `dl.acm.org` domain uses aggressive Cloudflare protection that blocks automated access, this skill uses reliable alternative APIs to fetch the same structured data.

## Data Sources

The skill combines data from two authoritative sources:

1. **Crossref API** (`api.crossref.org`)
   - Official DOI registry
   - Provides: title, authors with affiliations and ORCIDs, publication venue, event/conference name, page numbers, license info, citation counts, reference counts, funding information

2. **Semantic Scholar API** (`api.semanticscholar.org`)
   - AI-powered academic search engine
   - Provides: abstracts, enhanced citation counts, publication dates, venue classification

By merging these sources, the skill provides comprehensive metadata including abstracts that are not available through Crossref alone.

## Functions

### get_paper

Fetch complete metadata for a single paper by DOI.

**Parameters:**
- `doi` (required): DOI identifier in any format

**Returns:**
- `doi`: Normalized DOI
- `title`: Paper title
- `abstract`: Paper abstract (from Semantic Scholar)
- `authors`: List of authors with names, affiliations (when available), and ORCIDs
- `author_count`: Number of authors
- `year`: Publication year
- `type`: Publication type (e.g., "proceedings-article")
- `publisher`: Publisher name
- `venue`: Publication venue (journal/conference name)
- `event`: Conference/event name (for conference papers)
- `page`: Page range
- `url`: DOI URL
- `license`: License URL (when available)
- `citation_count`: Number of citations
- `reference_count`: Number of references
- `semantic_scholar_id`: Semantic Scholar paper ID
- `sources`: List of data sources used

**Example:**
```json
{
  "function": "get_paper",
  "doi": "10.1145/3641519.3657495"
}
```

### search_papers

Search for papers by title, author, or keywords.

**Parameters:**
- `query` (required): Search query
- `limit` (optional): Maximum results (default: 10)

**Returns:**
- `query`: Original search query
- `total`: Total matching papers
- `count`: Number of results returned
- `papers`: List of matching papers with metadata

**Example:**
```json
{
  "function": "search_papers",
  "query": "differentiable rendering lens design",
  "limit": 5
}
```

### get_citations

Get papers that cite a given paper.

**Parameters:**
- `doi` (required): DOI of the cited paper
- `limit` (optional): Maximum results (default: 20)

**Returns:**
- `doi`: Queried DOI
- `total`: Total citations
- `count`: Number of results returned
- `citations`: List of citing papers with metadata

**Example:**
```json
{
  "function": "get_citations",
  "doi": "10.1145/3641519.3657495"
}
```

### get_references

Get papers referenced by a given paper.

**Parameters:**
- `doi` (required): DOI of the paper
- `limit` (optional): Maximum results (default: 20)

**Returns:**
- `doi`: Queried DOI
- `total`: Total references
- `count`: Number of results returned
- `references`: List of referenced papers with metadata

**Example:**
```json
{
  "function": "get_references",
  "doi": "10.1145/3641519.3657495"
}
```

## DOI Format Support

The skill accepts DOIs in multiple formats:
- Pure DOI: `10.1145/3641519.3657495`
- DOI URL: `https://doi.org/10.1145/3641519.3657495`
- ACM DL URL: `https://dl.acm.org/doi/10.1145/3641519.3657495`

## Error Handling

The skill returns structured error responses rather than raising exceptions:
- Missing required parameters
- Invalid DOI format
- API failures (with details from both Crossref and Semantic Scholar when both fail)

## Limitations

- The skill cannot access paywalled full-text content
- Abstracts may not be available for all papers (depends on Semantic Scholar's coverage)
- Real-time citation counts may lag behind the actual ACM DL display
- Some very recent publications may not yet be indexed in external APIs

## Use Cases

- Retrieve paper metadata for bibliography management
- Find related work through citation networks
- Verify DOI information and author details
- Search for publications by topic or author
- Get paper abstracts for research summarization
