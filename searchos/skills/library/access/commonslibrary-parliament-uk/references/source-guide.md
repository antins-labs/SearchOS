# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# UK Parliament Commons Library - Research Briefings

This skill fetches research briefings from the UK Parliament House of Commons Library website (commonslibrary.parliament.uk).

## Overview

The House of Commons Library provides impartial research and information services to Members of Parliament. Their research briefings cover a wide range of topics including legislation, policy issues, and statistical analysis.

## Features

### Get Briefing (`get_briefing`)

Fetches a specific research briefing by its ID.

**Parameters:**
- `briefing_id` (required): The briefing ID (e.g., "SN04678", "CBP-9384")

**Returns:**
- `id`: Briefing ID
- `title`: Full title
- `description`: Meta description/summary
- `url`: Canonical URL
- `publication_info`: Date and author information
- `topics`: Associated topics/tags
- `downloads`: PDF download links with file sizes
- `related_posts`: Links to related briefings
- `breadcrumbs`: Navigation breadcrumbs
- `content`: Full text content
- `content_preview`: First 500 characters of content
- `structured_data`: JSON-LD structured data from the page

**Example:**
```json
{
  "function": "get_briefing",
  "briefing_id": "SN04678"
}
```

### List Briefings (`list_briefings`)

Lists the most recent research briefings with pagination support.

**Parameters:**
- `page` (optional): Page number (default: 1)

**Returns:**
- `briefings`: Array of briefing summaries
- `count`: Number of briefings on current page
- `page`: Current page number
- `pagination`: Pagination info (hasNext, hasPrev, nextUrl, prevUrl)
- `url`: Current page URL

**Example:**
```json
{
  "function": "list_briefings",
  "page": 1
}
```

### Search (`search`)

Searches for research briefings by keyword.

**Parameters:**
- `query` (required): Search query string

**Returns:**
- `query`: The search query
- `results`: Array of matching briefings
- `count`: Number of results
- `url`: Search results URL

**Example:**
```json
{
  "function": "search",
  "query": "brexit consumer protection"
}
```

## Briefing ID Format

Research briefing IDs typically follow these patterns:
- **SN####**: Standard Notes (e.g., SN04678)
- **CBP-####**: Commons Briefing Papers (e.g., CBP-9384)
- **CDP-####**: Commons Debate Packs (e.g., CDP-2025-0212)

The ID is case-insensitive and can include or omit hyphens.

## Technical Notes

- Uses Playwright browser automation to bypass cookie consent walls
- Extracts JSON-LD structured data for rich metadata
- Handles bot protection that blocks direct HTTP requests
- Extracts PDF download links with file sizes

## Common Topics

The library covers topics including:
- Business and industry
- Constitution and devolution
- Crime and justice
- Defence
- Economics and finance
- Education
- Environment
- Health
- Housing and planning
- International affairs
- Parliament and politics
- Science and technology
- Social policy
- Transport

## Error Handling

Returns structured error responses with:
- `success`: false
- `error`: Error message describing the issue
- `url`: The URL that was attempted (when applicable)

Common errors:
- Missing required parameter
- Briefing not found (invalid ID)
- Network/connection errors
