# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# PaperCopilot Access Skill

This skill fetches paper lists from [PaperCopilot](https://papercopilot.com), a website that hosts curated lists of accepted papers from major computer science conferences including SIGGRAPH, CVPR, ICCV, ICLR, NeurIPS, ICML, AAAI, ACL, EMNLP, and more.

## Features

- **List all papers** from a specific conference and year
- **Search papers by title** with keyword matching
- **Filter papers by session/area** (e.g., "3D Fabrication", "VR", "Neural Rendering")
- **Filter papers by status** (e.g., "Technical Paper", "Poster", "TOG Paper")
- **List available conferences** and their supported years

## Supported Conferences

| Conference ID | Full Name | Typical Years |
|--------------|-----------|---------------|
| siggraph | SIGGRAPH | 2022-2024 |
| cvpr | CVPR | 2013-2026 |
| iccv | ICCV | 2013-2025 |
| eccv | ECCV | 2018-2024 |
| iclr | ICLR | 2013-2025 |
| neurips | NeurIPS | 2020-2024 |
| icml | ICML | 2020-2024 |
| aaai | AAAI | 2021-2026 |
| acl | ACL | 2021-2025 |
| emnlp | EMNLP | 2021-2025 |

## Usage Examples

### List all papers from SIGGRAPH 2024

```json
{
  "function": "list_papers",
  "conference": "siggraph",
  "year": "2024"
}
```

Returns 274 papers with fields: number, title, url, session, status, abstract.

### Search for papers by title

```json
{
  "function": "search_paper",
  "conference": "siggraph",
  "year": "2024",
  "title": "neural"
}
```

Returns all papers with "neural" in the title.

### Filter papers by session/area

```json
{
  "function": "filter_by_session",
  "conference": "siggraph",
  "year": "2024",
  "session": "3D Fabrication"
}
```

Returns papers from the "3D Fabrication" session.

### Filter papers by status

```json
{
  "function": "filter_by_status",
  "conference": "siggraph",
  "year": "2024",
  "status": "Technical Paper"
}
```

Returns only Technical Papers (excludes TOG Papers, Posters, etc.).

### List available conferences

```json
{
  "function": "list_conferences"
}
```

Returns a list of supported conferences and their years.

## Data Source

Data is fetched from PaperCopilot's AJAX API endpoint. The site provides:
- Paper titles and links to official conference program pages
- Session/area classifications
- Acceptance status (Technical Paper, Poster, TOG Paper, etc.)
- Abstracts and keywords (when available)

## Notes

- The API returns papers in batches of 100. This skill automatically fetches all batches.
- Some conferences may not have session/area information populated.
- Paper URLs link to official conference program pages when available.
- The `track` parameter defaults to "main" and typically doesn't need to be changed.
