# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Jeff Huang Best Paper Awards

Access the comprehensive database of best paper awards in computer science maintained by Jeff Huang at [jeffhuang.com/best_paper_awards/](https://jeffhuang.com/best_paper_awards/).

## Overview

This skill provides structured access to a curated collection of **1,900+ best paper awards** from **32 top computer science conferences** spanning from **1996 to 2026**. The database includes:

- Paper titles
- Author names and affiliations
- Conference names (abbreviation and full name)
- Year of award
- Google Scholar links

## Available Functions

### `get_all_papers`
Retrieve all best paper awards with optional pagination.

**Parameters:**
- `limit` (optional): Maximum number of papers to return
- `offset` (optional): Number of papers to skip (for pagination)

**Example:**
```json
{
  "function": "get_all_papers",
  "limit": 10,
  "offset": 0
}
```

### `get_papers_by_conference`
Get all best paper awards for a specific conference.

**Parameters:**
- `conference` (required): Conference abbreviation (uppercase)
- `limit` (optional): Maximum number of results
- `offset` (optional): Number of results to skip

**Example:**
```json
{
  "function": "get_papers_by_conference",
  "conference": "ICML"
}
```

### `get_papers_by_year`
Get all best paper awards for a specific year.

**Parameters:**
- `year` (required): Year (1996-2026)
- `limit` (optional): Maximum number of results
- `offset` (optional): Number of results to skip

**Example:**
```json
{
  "function": "get_papers_by_year",
  "year": "2023"
}
```

### `search_papers`
Search papers by title or author keywords.

**Parameters:**
- `query` (required): Search keyword(s)
- `search_in` (optional): Search scope - `title`, `authors`, or `all` (default)
- `limit` (optional): Maximum number of results
- `offset` (optional): Number of results to skip

**Example:**
```json
{
  "function": "search_papers",
  "query": "transformer",
  "search_in": "title"
}
```

### `get_statistics`
Get database statistics including paper counts per conference and year.

**Example:**
```json
{
  "function": "get_statistics"
}
```

### `get_conferences`
Get list of all conferences in the database with paper counts.

**Example:**
```json
{
  "function": "get_conferences"
}
```

## Supported Conferences

| Abbr | Full Name | Papers |
|------|-----------|--------|
| CHI | Human-Computer Interaction | 491 |
| ICSE | Software Engineering | 188 |
| FSE | Software Engineering | 137 |
| PLDI | Programming Languages | 84 |
| S&P | Security and Privacy | 69 |
| UIST | User Interface | 61 |
| ICML | Machine Learning | 57 |
| AAAI | Artificial Intelligence | 52 |
| STOC | Theory | 51 |
| IJCAI | Artificial Intelligence | 50 |
| FOCS | Theory | 48 |
| ACL | Natural Language Processing | 47 |
| INFOCOM | Networking | 47 |
| NeurIPS | Machine Learning | 45 |
| SOSP | Operating Systems | 43 |
| NSDI | Networking | 40 |
| OSDI | Operating Systems | 39 |
| SIGMOD | Databases | 36 |
| CVPR | Computer Vision | 35 |
| PODS | Databases | 35 |
| VLDB | Databases | 33 |
| SIGIR | Information Retrieval | 31 |
| WWW | World Wide Web | 30 |
| KDD | Data Mining | 29 |
| SODA | Theory | 28 |
| SIGMETRICS | Performance | 26 |
| CIKM | Knowledge Management | 24 |
| SIGCOMM | Networking | 23 |
| ICCV | Computer Vision | 21 |
| SIGGRAPH | Graphics | 20 |
| MOBICOM | Mobile | 19 |
| ISCA | Architecture | 8 |

## Response Format

All paper queries return results in the following structure:

```json
{
  "success": true,
  "count": 10,
  "papers": [
    {
      "year": "2023",
      "conference": "ICML",
      "conference_name": "Machine Learning",
      "title": "Paper Title Here",
      "authors": "Author Name, Institution; Co-author Name, Institution",
      "scholar_url": "https://scholar.google.com/..."
    }
  ]
}
```

## Notes

- This is a read-only skill for accessing publicly available academic award data
- The source data is curated and maintained by Jeff Huang
- Author affiliations are included when available
- Google Scholar links are provided for citation lookup
- Papers with many authors have full author lists expanded from hidden sections
