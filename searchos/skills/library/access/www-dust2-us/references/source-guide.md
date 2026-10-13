# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Dust2.us News Access Skill

This skill extracts Counter-Strike news articles from [Dust2.us](https://www.dust2.us/), a leading North American Counter-Strike news and coverage site.

## Features

### get_article
Fetches and parses a single news article, extracting:
- **Title** - Article headline
- **Author** - Article author name
- **Publication date** - ISO 8601 format and Unix timestamp
- **Article body** - Full text content as paragraphs and lists
- **Featured image** - Image URL and credit/attribution
- **Meta description** - Article summary
- **Related articles** - "Also read" links

**Parameters:**
- `url` (required): The article URL (can be relative path like `/news/75298/...` or full URL)

**Example:**
```python
result = await execute({
    'function': 'get_article',
    'url': 'https://www.dust2.us/news/75298/breaking-valve-announce-the-return-of-cache-to-active-duty-after-'
}, ctx)

# Or with relative URL:
result = await execute({
    'function': 'get_article',
    'url': '/news/75298/breaking-valve-announce-the-return-of-cache-to-active-duty-after-'
}, ctx)
```

**Response structure:**
```python
{
    'url': 'https://www.dust2.us/news/75298/...',
    'source': 'dust2.us',
    'title': 'Breaking: Valve announce the return of Cache to Active Duty after seven years',
    'author': 'Mnmzzz',
    'published_date': '2026-06-22T19:03:00',
    'published_timestamp': 1782154980000,
    'image_url': 'https://img-cdn.hltv.org/...',
    'image_credit': 'Credit: Valve',
    'description': 'Cachecels rejoice!',
    'body': 'Full article text...',
    'body_paragraphs': ['Paragraph 1', 'Paragraph 2', ...],
    'lists': ['Dust2', 'Mirage', 'Inferno', ...],
    'related_articles': [{'url': '...', 'title': '...'}, ...]
}
```

### get_news_listing
Fetches the current news listing from the Dust2.us homepage.

**Parameters:** None

**Example:**
```python
result = await execute({
    'function': 'get_news_listing'
}, ctx)
```

**Response structure:**
```python
{
    'source': 'dust2.us',
    'articles': [
        {
            'url': 'https://www.dust2.us/news/76188/wildcard-defend-their-bounty-and-take-down-alliance-2-0',
            'title': 'Wildcard Defend Their Bounty And Take Down Alliance 2 0',
            'slug': 'wildcard-defend-their-bounty-and-take-down-alliance-2-0'
        },
        ...
    ],
    'count': 30
}
```

## Implementation Notes

- Uses direct HTTP requests with BeautifulSoup parsing (no JavaScript rendering required)
- Article titles in the listing are derived from URL slugs
- Timestamps are converted from milliseconds to ISO 8601 format
- Handles both relative and absolute URLs
- The news listing is fetched from the homepage as `/news/` returns 404

## Error Handling

Returns structured error objects with descriptive messages for:
- Missing required parameters
- Failed HTTP requests
- Parsing failures
- Unknown function names

## Source

[Dust2.us](https://www.dust2.us/) is a premier North American Counter-Strike news site covering professional scene coverage, roster moves, tournament results, and game updates.
