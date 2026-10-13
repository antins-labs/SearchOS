# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# NME.com Article Extractor

This skill extracts structured article content from NME.com news articles.

## Features

- **Title Extraction**: Extracts the article headline from both HTML and JSON-LD structured data
- **Published Time**: Retrieves publication date and time in multiple formats
- **Author Information**: Extracts the article author name
- **Full Content**: Extracts article body as clean markdown text
- **Metadata**: Includes keywords, article sections, and modification dates

## Usage

### fetch_article

Fetches and extracts article content from an NME.com URL.

**Parameters:**
- `url` (string, required): The NME.com article URL

**Example:**
```python
result = await execute({
    'function': 'fetch_article',
    'url': 'https://www.nme.com/news/music/blackpink-lisa-launch-own-artist-management-company-lloud-3584291'
}, ctx)
```

**Returns:**
```python
{
    'url': 'https://www.nme.com/news/music/...',
    'title': 'BLACKPINK's Lisa launches her own management company, LLOUD',
    'headline': 'BLACKPINK's Lisa launches her own management company, LLOUD',
    'author': 'Puah Ziwei',
    'published_time': '8th February 2024',
    'published_datetime': '2024-02-08T08:10:56+00:00',
    'published_time_formatted': '2024-02-08 08:10:56 UTC',
    'date_modified': '2024-02-08T08:44:30+00:00',
    'keywords': ['K-pop'],
    'article_section': ['Music News', 'News'],
    'content': '# Article Title\n\n**Author:** ...\n\n**Published:** ...\n\n---\n\nArticle content...',
    'word_count': 291,
    'paragraph_count': 9,
    'error': None
}
```

## Supported URLs

This skill works with NME.com article URLs, typically in the format:
- `https://www.nme.com/news/music/*`
- `https://www.nme.com/news/film/*`
- `https://www.nme.com/news/gaming/*`
- Other NME.com article URLs

## Data Sources

The extractor uses multiple sources for reliability:
1. **JSON-LD Structured Data**: Primary source for headline, author, dates, and metadata
2. **HTML Elements**: Fallback for title and publication time display
3. **Article Body**: Extracted from `<article>` element paragraphs

## Error Handling

Returns an error field with descriptive message when:
- URL is missing or invalid
- URL is not from nme.com domain
- HTTP request fails or times out
- Article content cannot be parsed
