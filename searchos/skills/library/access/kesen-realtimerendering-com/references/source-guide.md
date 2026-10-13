# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Ke-Sen Huang's Computer Graphics Paper Collection

This skill retrieves structured paper listings from Ke-Sen Huang's manually maintained
computer graphics conference paper collection at [kesen.realtimerendering.com](https://kesen.realtimerendering.com).

## Overview

The site hosts one of the most comprehensive collections of graphics research papers,
particularly for SIGGRAPH conferences from 2005 to 2026. Each paper entry includes:

- **Title**: The paper's full title
- **Authors**: List of authors with their affiliations
- **Resource Links**: Various types including:
  - Paper Abstract
  - Author Preprint (PDF)
  - Paper Video
  - Demo Program or Source Code
  - Paper Data
  - Paper Presentation

## Available Functions

### list_conferences

Lists all available conference paper collections.

**Parameters:** None

**Returns:**
- List of conferences with year, name, and URL
- Currently includes SIGGRAPH 2005-2026

**Example:**
```json
{
  "function": "list_conferences"
}
```

### list_papers

Lists all papers from a specific SIGGRAPH year.

**Parameters:**
- `year` (required): SIGGRAPH year, 2005-2026

**Returns:**
- Conference name and year
- Complete list of papers with titles, authors, and links
- Total paper count

**Example:**
```json
{
  "function": "list_papers",
  "year": 2024
}
```

### get_paper

Finds a specific paper by title (partial match supported).

**Parameters:**
- `year` (required): SIGGRAPH year, 2005-2026
- `title` (required): Paper title or title fragment

**Returns:**
- Matching paper(s) with full details
- If multiple matches, returns all matching papers

**Example:**
```json
{
  "function": "get_paper",
  "year": 2024,
  "title": "Gaussian Splatting"
}
```

### search_papers

Searches papers by keyword in title or author names.

**Parameters:**
- `year` (required): SIGGRAPH year, 2005-2026
- `query` (required): Search keyword

**Returns:**
- List of matching papers
- Match count and total papers in collection

**Example:**
```json
{
  "function": "search_papers",
  "year": 2024,
  "query": "neural"
}
```

## Data Structure

Each paper entry has the following structure:

```json
{
  "title": "Paper Title",
  "links": [
    {"type": "Paper Abstract", "url": "https://..."},
    {"type": "Author Preprint", "url": "https://..."},
    {"type": "Paper Video", "url": "https://..."}
  ],
  "authors_text": "Author1, Author2 (Affiliation1), Author3 (Affiliation2)",
  "authors": [
    {"name": "Author1", "url": "https://author1-homepage.com"},
    {"name": "Author2", "url": "https://author2-homepage.com"}
  ]
}
```

## Notes

- The site uses a simple HTML structure with `<dt>` (definition term) for paper titles
  and `<dd>` (definition description) for author information
- Paper links are indicated by images with alt text describing the resource type
- Author names link to their personal/institutional homepages
- The collection is manually maintained and updated around conference dates
- SIGGRAPH 2026 may have limited content as it's a future conference
