# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# WorldAtlas Article Parser

This skill extracts structured geographical content from WorldAtlas.com articles, with specialized handling for country border information.

## Features

- **Article Extraction**: Parses full article content including title, author, publication date, and structured sections
- **Border Information**: Automatically extracts lists of bordering countries from relevant articles
- **Schema.org Support**: Leverages structured data when available for accurate extraction
- **Search Functionality**: Search for articles by topic

## Functions

### fetch_article

Fetches and parses a specific WorldAtlas article URL.

**Parameters:**
- `url` (required): The full URL of the WorldAtlas article

**Returns:**
- `title`: Article headline
- `description`: Article description/summary
- `author`: Author name
- `date_published`: Publication date
- `date_modified`: Last modified date
- `content`: Full article text
- `sections`: Parsed sections with headings and content
- `bordering_countries`: Extracted list of bordering countries (if applicable)

**Example:**
```json
{
  "function": "fetch_article",
  "url": "https://www.worldatlas.com/articles/what-countries-border-norway.html"
}
```

### search_articles

Searches for WorldAtlas articles matching a query.

**Parameters:**
- `query` (required): Search terms
- `max_results` (optional): Maximum results to return (default: 10)

**Returns:**
- `results`: List of articles with title and URL
- `count`: Number of results found

**Example:**
```json
{
  "function": "search_articles",
  "query": "countries border france"
}
```

### get_bordering_countries

Gets countries that border a specific country.

**Parameters:**
- `country` (required): Name of the country

**Returns:**
- `country`: The queried country
- `bordering_countries`: List of bordering countries
- `description`: Article summary
- `content`: Full article content
- `sections`: Detailed sections about each border

**Example:**
```json
{
  "function": "get_bordering_countries",
  "country": "Norway"
}
```

## Content Structure

Articles are parsed into structured sections when they contain numbered headings (e.g., "1. Norway-Sweden Border"). Each section includes:
- `heading`: Section title
- `content`: Section text content

## Bordering Countries Detection

The skill automatically detects and extracts bordering country lists from articles about country borders. It recognizes patterns like:
- "shares its land border with three countries; Sweden, Russia, and Finland"
- "Three nations share a land border with X and they include Croatia, Serbia, and Montenegro"

## Technical Details

- Uses Playwright for browser automation to handle JavaScript-rendered content
- Prioritizes Schema.org structured data for accurate extraction
- Falls back to DOM parsing when structured data is unavailable
- Handles timeouts gracefully for slow-loading pages
