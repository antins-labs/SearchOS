# Sina Finance Article Extractor

Extracts structured article content from Sina Finance (finance.sina.com.cn) stock news pages.

## Overview

This skill specifically targets Sina Finance articles that contain TOP50 ranking lists and other financial news. It successfully extracts article content that generic readers often fail to parse due to the site's complex navigation structure.

## Supported URLs

- Stock news articles: `https://finance.sina.com.cn/stock/relnews/*/YYYY-MM-DD/doc-*.shtml`
- General finance articles from finance.sina.com.cn domain

## Features

### Article Extraction

Extracts comprehensive article data:

- **Metadata**: Title, description, keywords, author, source, publish/update times
- **Content**: Full text, individual paragraphs, content length
- **Images**: All images with URLs and alt text
- **Categorization**: Auto-detects article category from URL (stock_hk, stock_us, forex, etc.)
- **Article ID**: Extracts unique article ID from URL

### Data Fields

Returned data includes:

- `title`: Article title (cleaned, without site suffix)
- `description`: Meta description
- `keywords`: List of article keywords
- `author`: Article author
- `source`: Content source/publisher
- `published_time`: Publication timestamp
- `updated_time`: Last update timestamp
- `category`: Article category (stock, stock_hk, stock_us, forex, future, fund)
- `content`: Full article text
- `paragraphs`: List of individual paragraphs
- `images`: List of image objects with url, alt, title
- `content_length`: Character count of content
- `paragraph_count`: Number of paragraphs
- `image_count`: Number of images

## Use Cases

- Extract TOP50 ranking lists from property service company articles
- Parse financial news articles for content analysis
- Extract stock market reports and analyses
- Collect article metadata for research purposes

## Example

```python
result = await execute({
    "function": "get_article",
    "url": "https://finance.sina.com.cn/stock/relnews/hk/2025-05-06/doc-inevrvkt0394044.shtml",
    "include_images": true,
    "include_content": true
})

# Returns structured data:
{
    "success": true,
    "title": "2025年4月中国物业服务企业品牌传播TOP50",
    "author": "中指物业研究",
    "category": "stock_hk",
    "content": "...",
    "paragraphs": [...],
    "images": [...],
    ...
}
```

## Error Handling

- Returns structured error responses for:
  - Missing required parameters
  - Invalid domain (must be sina.com.cn)
  - 404 not found articles
  - HTTP/network errors
  - Parse failures

All errors include the URL and article ID (if available) for debugging.

## Notes

- The skill uses direct HTTP requests without browser automation for efficiency
- Content is extracted from the `#artibody` element which is standard for Sina articles
- Images with protocol-relative URLs (`//n.sinaimg.cn/...`) are converted to HTTPS
- The extractor handles both standard meta tags and Sina-specific Weibo meta tags
- Article titles are cleaned by removing site suffixes like "|物业_新浪财经_新浪网"