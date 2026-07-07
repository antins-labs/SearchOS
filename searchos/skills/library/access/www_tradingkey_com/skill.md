# TradingKey Article Fetcher

Fetches analysis and news articles from TradingKey (www.tradingkey.com), a financial news and analysis platform covering stocks, markets, economics, politics, and more.

## Features

- **Full Article Extraction**: Retrieves title, author, publication date, keywords, and complete article content
- **Structured Data Extraction**: Extracts tables, headings, key points, and bullet lists
- **Financial Data Parsing**: Identifies percentages, monetary figures, and stock tickers mentioned in articles
- **Article Search**: Browse articles by category (stocks, politics, economics, commodities, crypto, forex)
- **Rich Metadata**: Extracts JSON-LD structured data including article section, images, and modification dates

## Functions

### get_article

Fetches a single article by URL and extracts all available structured data.

**Parameters:**
- `url` (required): Full article URL, e.g., `https://www.tradingkey.com/analysis/stocks/us-stocks/261975340-mu-q3-earnings-preview-june-2026-tradingkey`

**Returns:**
```json
{
  "status": "success",
  "url": "https://www.tradingkey.com/...",
  "title": "Article Title",
  "description": "Article description/summary",
  "author": "Author Name",
  "date_published": "2026-06-21T12:00:00+00:00",
  "date_modified": "2026-06-18T08:46:16+00:00",
  "section": "US Stocks,Stocks",
  "keywords": ["keyword1", "keyword2"],
  "image_url": "https://resource.tradingkey.com/...",
  "content": "Full article text...",
  "word_count": 1500,
  "headings": [
    {"level": "h2", "text": "Section Title"},
    ...
  ],
  "tables": [
    {
      "headers": ["Column1", "Column2"],
      "rows": [["data1", "data2"], ...]
    },
    ...
  ],
  "key_points": ["Point 1", "Point 2", ...],
  "percentages": ["20%", "700%", ...],
  "monetary_figures": ["$34.66 billion", "$1,200", ...],
  "stock_tickers": ["MU", "NVDA", ...]
}
```

**Error Responses:**
- `ARTICLE_GONE`: Article no longer available (HTTP 410)
- `HTTP_ERROR`: Other HTTP errors
- `TIMEOUT`: Request timed out
- `NETWORK_ERROR`: Network connection issues

### search_articles

Browses articles by category, optionally filtered by a search query.

**Parameters:**
- `category` (optional): Category to browse - stocks, politics, economics, commodities, crypto, forex, or news
- `query` (optional): Filter articles by title (case-insensitive substring match)
- `limit` (optional, default 10): Maximum number of results

**Returns:**
```json
{
  "status": "success",
  "query": "micron",
  "category": "stocks",
  "total": 5,
  "articles": [
    {
      "title": "Article Title",
      "url": "https://www.tradingkey.com/...",
      "article_id": "261975340",
      "image_url": "https://..."
    },
    ...
  ]
}
```

## Supported Categories

- `stocks`: Stock market analysis (US and international)
- `politics`: Political analysis and policy impact (America, Middle East, etc.)
- `economics`: Economic indicators and macro analysis
- `commodities`: Commodity market analysis
- `crypto`: Cryptocurrency analysis
- `forex`: Foreign exchange market analysis
- `news`: General market news

## Use Cases

1. **Financial Research**: Extract detailed analysis articles with key financial metrics and analyst commentary
2. **Market Monitoring**: Search for articles about specific stocks or topics
3. **Data Extraction**: Parse tables of historical data (e.g., government shutdown history, earnings comparisons)
4. **Content Aggregation**: Build feeds of the latest analysis from various categories

## Notes

- TradingKey articles are primarily focused on US markets but include global coverage
- Articles often contain structured tables with historical or comparative data
- The site uses server-side rendering; no JavaScript execution is needed
- Rate limiting may apply for rapid successive requests
- Some older articles may return HTTP 410 (gone) status

## Example Usage

**Fetch an article:**
```python
result = await execute({
    "function": "get_article",
    "url": "https://www.tradingkey.com/analysis/stocks/us-stocks/261975340-mu-q3-earnings-preview-june-2026-tradingkey"
})
```

**Search articles in a category:**
```python
result = await execute({
    "function": "search_articles",
    "category": "stocks",
    "query": "nvidia",
    "limit": 20
})
```

**Browse latest politics articles:**
```python
result = await execute({
    "function": "search_articles",
    "category": "politics",
    "limit": 10
})
```