# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# ACL Anthology Access Skill

This skill fetches structured paper records from the ACL Anthology (aclanthology.org), a comprehensive repository of computational linguistics and natural language processing research papers.

## Features

- **Paper Metadata Extraction**: Retrieves complete paper information including:
  - Title
  - Authors (full list)
  - Abstract
  - PDF download link
  - DOI
  - Publication date (year/month)
  - Venue/Conference name
  - Page numbers
  - Editors
  - Publisher
  - BibTeX citation key
  - Awards (if any)
  - Video links (if available)

- **BibTeX Export**: Optionally fetches the BibTeX citation for easy reference management

## Supported Functions

### `get_paper`

Fetches a single paper by its ACL Anthology ID.

**Parameters:**
- `anthology_id` (required): The ACL Anthology paper ID
  - Format: `YYYY.VENUE-TYPE.NUMBER` (e.g., `2024.acl-long.788`)
  - Common patterns:
    - `2024.acl-long.123` - ACL long papers
    - `2023.acl-short.45` - ACL short papers
    - `2022.emnlp-main.100` - EMNLP main papers
    - `P02-1040` - Older format papers
- `include_bibtex` (optional): Set to `true` to include BibTeX citation (default: `false`)

**Example Usage:**

```json
{
  "function": "get_paper",
  "anthology_id": "2024.acl-long.788"
}
```

With BibTeX:

```json
{
  "function": "get_paper",
  "anthology_id": "2024.acl-long.788",
  "include_bibtex": true
}
```

**Sample Response:**

```json
{
  "success": true,
  "anthology_id": "2024.acl-long.788",
  "url": "https://aclanthology.org/2024.acl-long.788/",
  "title": "Semisupervised Neural Proto-Language Reconstruction",
  "authors": ["Liang Lu", "Peirong Xie", "David R. Mortensen"],
  "abstract": "Existing work implementing comparative reconstruction...",
  "pdf_url": "https://aclanthology.org/2024.acl-long.788.pdf",
  "doi": "10.18653/v1/2024.acl-long.788",
  "venue": "Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)",
  "year": "2024",
  "month": "August",
  "pages": "14715–14759",
  "publisher": "Association for Computational Linguistics",
  "award": "Best Paper Award",
  "bibtex_url": "https://aclanthology.org/2024.acl-long.788.bib"
}
```

## Finding ACL Anthology IDs

ACL Anthology IDs can be found in the paper URLs:
- URL: `https://aclanthology.org/2024.acl-long.788/`
- ID: `2024.acl-long.788`

Browse papers at: https://aclanthology.org/

## Notes

- The site uses Google Custom Search for search functionality, which requires JavaScript and is not directly accessible via HTTP requests
- For browsing papers by venue/volume, visit the ACL Anthology website directly
- Paper metadata is extracted from structured HTML and meta tags for reliability
- BibTeX is fetched from the `.bib` endpoint (e.g., `https://aclanthology.org/2024.acl-long.788.bib`)
