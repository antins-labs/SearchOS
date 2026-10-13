# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# InvestingNews.com Access Skill

This skill extracts structured data about rare earth reserves and investing articles from investingnews.com.

## Functions

### get_reserves

Extracts rare earth reserves data by country from the dedicated reserves page.

**Returns:**
- Article metadata (title, author, publication date)
- List of top 7 countries with:
  - Country name
  - Rank
  - Reserves (in million metric tons)
  - Production (if available)
  - Detailed description paragraphs
- FAQ section (if available)

**Example:**
```python
result = await execute({'function': 'get_reserves'}, ctx)
# Returns structured data for China, Brazil, Australia, Russia, Vietnam, United States, Greenland
```

### get_articles

Retrieves a list of recent rare earth investing articles from the tag page.

**Parameters:**
- `limit` (optional): Maximum number of articles to return (default: 20)

**Returns:**
- List of articles with title and URL

**Example:**
```python
result = await execute({'function': 'get_articles', 'limit': 10}, ctx)
```

### get_article

Extracts full content from a specific article URL.

**Parameters:**
- `url` (required): The full URL of the article

**Returns:**
- Article metadata (title, author, publication date, description)
- Content paragraphs (first 10)
- Word count

**Example:**
```python
result = await execute({
    'function': 'get_article',
    'url': 'https://investingnews.com/daily/resource-investing/critical-metals-investing/rare-earth-investing/top-canadian-rare-earths-stocks/'
}, ctx)
```

## Data Sources

- Rare Earth Reserves: `https://investingnews.com/daily/resource-investing/critical-metals-investing/rare-earth-investing/rare-earth-reserves-country/`
- Article List: `https://investingnews.com/tag/rare-earth-investing`

## Notes

- The skill uses HTTP requests with BeautifulSoup for HTML parsing
- No JavaScript rendering required - all content is available in the static HTML
- Reserve data is extracted from structured headings and paragraphs in the article
- The reserves article is regularly updated with the latest data from USGS and company reports
