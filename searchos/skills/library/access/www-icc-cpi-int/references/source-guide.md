# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# ICC (International Criminal Court) Access Skill

This skill provides access to the International Criminal Court website at [www.icc-cpi.int](https://www.icc-cpi.int), fetching news articles, court records, and search results while bypassing Cloudflare protection.

## Features

- **News Articles**: Fetch individual news articles with full content and related documents
- **News Listing**: List recent news articles from the ICC
- **Search**: Search across the ICC website for documents, cases, and pages
- **Court Records**: Access individual court documents with metadata and PDF links
- **RSS Feeds**: Subscribe to news or court records feeds

## Functions

### get_news_article

Fetches a single news article from the ICC website.

**Parameters:**
- `url` (required): Full URL of the news article

**Returns:**
- `title`: Article headline
- `date`: Publication date
- `content`: Full article text
- `documents`: List of related documents with titles and URLs
- `url`: Source URL

**Example:**
```json
{
  "function": "get_news_article",
  "url": "https://www.icc-cpi.int/news/icc-appeals-chamber-confirms-trial-chamber-decision-acquitting-laurent-gbagbo-and-charles-ble"
}
```

### list_news

Lists recent news articles from the ICC.

**Parameters:**
- `limit` (optional): Maximum number of articles to return (default: 20)

**Returns:**
- `news`: Array of news items with title and URL
- `count`: Number of results

**Example:**
```json
{
  "function": "list_news",
  "limit": 10
}
```

### search

Searches the ICC website for documents, cases, and pages.

**Parameters:**
- `query` (required): Search query string
- `limit` (optional): Maximum number of results (default: 20)

**Returns:**
- `query`: Original search query
- `results`: Array of search results with title, URL, and snippet
- `count`: Number of results

**Example:**
```json
{
  "function": "search",
  "query": "war crimes Ukraine"
}
```

### get_document

Fetches a court record or document from the ICC.

**Parameters:**
- `url` (required): Full URL of the document page

**Returns:**
- `title`: Document title
- `document_number`: ICC document number (e.g., ICC-02/11-01/15-1400)
- `date`: Document date
- `pdfs`: List of PDF download links
- `related_documents`: Related court documents
- `url`: Source URL

**Example:**
```json
{
  "function": "get_document",
  "url": "https://www.icc-cpi.int/Pages/record.aspx?docNo=ICC-02/11-01/15-1400"
}
```

### get_rss

Fetches RSS feed from the ICC.

**Parameters:**
- `feed_type` (optional): Type of feed - "news" or "records" (default: "news")
- `limit` (optional): Maximum number of items (default: 20)

**Returns:**
- `feed_type`: Type of feed retrieved
- `items`: Array of RSS items with title, URL, description, and publication date
- `count`: Number of items

**Example:**
```json
{
  "function": "get_rss",
  "feed_type": "news",
  "limit": 15
}
```

## Notes

- The ICC website uses Cloudflare protection which blocks direct HTTP requests
- This skill uses browser automation to bypass the protection
- All requests include proper user agent and browser headers
- Document URLs typically follow the pattern: `https://www.icc-cpi.int/Pages/record.aspx?docNo=ICC-XX/XX-XX/XX-XXXX`
- News article URLs follow the pattern: `https://www.icc-cpi.int/news/[article-slug]`

## Common Use Cases

1. **Track ICC News**: Use `list_news` to get recent press releases and announcements
2. **Research Cases**: Use `search` to find documents related to specific cases or situations
3. **Access Court Documents**: Use `get_document` to retrieve specific court filings and judgments
4. **Monitor Updates**: Use `get_rss` to subscribe to news or court records feeds
5. **Read Full Articles**: Use `get_news_article` to get complete news article content with related documents
