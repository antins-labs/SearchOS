# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Encyclopaedia Iranica Article Extractor

This skill fetches scholarly encyclopedia entries from [Encyclopaedia Iranica](https://www.iranicaonline.org), a comprehensive research tool dedicated to the study of Iranian civilization in the Middle East, the Caucasus, Central Asia, and the Indian subcontinent.

## Features

- **Article Retrieval**: Extracts full article content with structured metadata
- **Search**: Search across the encyclopedia's 9,000+ entries
- **Metadata Extraction**: Captures author, publication dates, volume/fascicle info, DOI
- **Bibliography**: Extracts bibliographic references
- **Related Articles**: Identifies linked related entries

## Functions

### get_article

Retrieve a single encyclopedia article.

**Parameters:**
- `url` (string, optional): Full article URL
- `article_slug` (string, optional): Article identifier (e.g., "ayyubids")

**Example:**
```json
{
  "function": "get_article",
  "article_slug": "ayyubids"
}
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.iranicaonline.org/articles/ayyubids/",
  "title": "AYYUBIDS",
  "author": "R. Stephen Humphreys",
  "published_date": "December 15, 1987",
  "last_updated": "January 13, 2017",
  "volume": "III",
  "fascicle": "2",
  "pages": "164-167",
  "doi": "https://doi.org/10.1163/2330-4804_EIRO_COM_6165",
  "topic": "history-medieval",
  "body_paragraphs": ["...", "..."],
  "body_text": "Full article text...",
  "bibliography": ["...", "..."],
  "citation": "Citation format...",
  "related_articles": [
    {"url": "...", "title": "..."}
  ],
  "sections": [
    {"level": "h3", "text": "Bibliography"}
  ]
}
```

### search_articles

Search for articles in the encyclopedia.

**Parameters:**
- `query` (string, required): Search keywords

**Example:**
```json
{
  "function": "search_articles",
  "query": "saladin"
}
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.iranicaonline.org/?s=saladin",
  "results": [
    {
      "url": "https://www.iranicaonline.org/articles/ayyubids/",
      "title": "AYYUBIDS",
      "description": "..."
    }
  ],
  "total_results": 15
}
```

## Error Handling

- **404 Not Found**: Returns `{"error": "Article not found", "error_type": "not_found", "status": 404}`
- **Missing Parameters**: Returns `{"error": "..."}` with descriptive message

## Notes

- The site requires browser automation due to JavaScript rendering
- Articles contain scholarly content with transliterated Arabic/Persian terms
- Bibliography sections are extracted separately from the main body
- Related article links are deduplicated and limited to 20 entries
