# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Bundesgesundheitsministerium Cannabis FAQ Skill

This skill extracts structured FAQ question-answer pairs from the German Federal Ministry of Health's Cannabis Act FAQ page.

## Source

**URL**: https://www.bundesgesundheitsministerium.de/en/themen/cannabis/faq-cannabis-act

The page contains comprehensive information about Germany's cannabis legalization, organized into thematic sections with expandable Q&A accordions.

## Available Functions

### `get_all`

Fetches all FAQ Q&A pairs organized by section.

**Example:**
```json
{
  "function": "get_all"
}
```

**Returns:**
- `data.sections`: Array of section objects, each containing:
  - `title`: Section name
  - `qa_pairs`: Array of question-answer objects
  - `question_count`: Number of questions in section
- `data.total_questions`: Total number of Q&A pairs
- `summary`: Overview with section names and question counts

### `search`

Searches for Q&A pairs matching a query string (case-insensitive).

**Parameters:**
- `query` (required): Search term
- `limit` (optional): Maximum results (default: 10)

**Example:**
```json
{
  "function": "search",
  "query": "cultivation",
  "limit": 5
}
```

**Returns:**
- `results`: Array of matching Q&A pairs with section context
- `total_matches`: Number of matches found

### `get_section`

Gets all Q&A pairs from a specific section.

**Parameters:**
- `section` (required): Section name (partial match, case-insensitive)

**Example:**
```json
{
  "function": "get_section",
  "section": "cultivation associations"
}
```

**Returns:**
- `section`: Section object with all Q&A pairs

### `get_qa`

Gets a specific Q&A pair by index.

**Parameters:**
- `section_index` (required): Zero-based section index
- `qa_index` (required): Zero-based question index within section

**Example:**
```json
{
  "function": "get_qa",
  "section_index": 0,
  "qa_index": 0
}
```

**Returns:**
- `qa`: Single Q&A pair with section context

## Sections Available

The FAQ contains 53 questions across 11 sections:

| Index | Section | Questions |
|-------|---------|-----------|
| 0 | General | 5 |
| 1 | Health and consumer protection | 3 |
| 2 | Child and youth protection | 4 |
| 3 | Provisions on the possession of cannabis | 1 |
| 4 | Private self-cultivation | 5 |
| 5 | Cultivation associations | 21 |
| 6 | Medicinal cannabis | 6 |
| 7 | Road traffic | 1 |
| 8 | Addiction prevention | 3 |
| 9 | Criminal law | 3 |
| 10 | Research | 1 |

## Response Format

All responses include a `success` boolean field. On failure, an `error` field contains the error message.

```json
{
  "success": true,
  "data": { ... }
}
```

## Example Use Cases

### Find questions about possession limits
```json
{"function": "search", "query": "25 grams"}
```

### Get all questions about cultivation associations
```json
{"function": "get_section", "section": "cultivation associations"}
```

### Get specific Q&A about road traffic rules
```json
{"function": "get_qa", "section_index": 7, "qa_index": 0}
```

## Notes

- The page is in English; all extracted content is in English
- The FAQ is regularly updated as regulations evolve
- Answers are extracted as plain text from the accordion content
- The skill uses direct HTTP requests; no JavaScript rendering required
