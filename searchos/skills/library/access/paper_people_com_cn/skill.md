# People's Daily Digital Newspaper Access Skill

This skill provides access to the People's Daily (人民日报) digital newspaper at paper.people.com.cn, allowing you to fetch article content, browse layout pages, navigate by date, and access the current edition.

## Site Overview

The People's Daily digital newspaper website provides access to the full content of the daily newspaper. Each day's edition is organized into multiple pages (版面), each containing several articles. The site uses consistent URL patterns:

### URL Patterns

- **Article URLs**: `https://paper.people.com.cn/rmrb/pc/content/YYYYMM/DD/content_XXXXXXX.html`
  - Example: `https://paper.people.com.cn/rmrb/pc/content/202601/20/content_30133983.html`

- **Layout URLs**: `http://paper.people.com.cn/rmrb/pc/layout/YYYYMM/DD/node_XX.html`
  - Example: `http://paper.people.com.cn/rmrb/pc/layout/202601/20/node_11.html`
  - `node_XX` represents the page number (01-20 typically)

- **Main Index**: `http://paper.people.com.cn/rmrb/pc/layout/index.html`
  - Shows today's edition with links to all pages

## Functions

### 1. get_article

Fetches the full content of a specific article.

**Parameters:**
- `url` (required): The full URL of the article page

**Returns:**
```json
{
  "title": "神舟二十号飞船安全顺利返回东风着陆场",
  "content": "本报酒泉1月19日电  （记者安博文、刘诗瑶）据中国载人航天工程办公室消息...",
  "meta": {
    "publishdate": "2026-01-20",
    "contentid": "rmrbdzb_30133983"
  },
  "date_info": {
    "newspaper_date": "2026年01月20日",
    "page_number": "11",
    "page_section": "第11版：文化"
  },
  "navigation": {
    "previous": "https://paper.people.com.cn/rmrb/pc/content/202601/20/content_30133982.html",
    "next": "https://paper.people.com.cn/rmrb/pc/content/202601/20/content_30133984.html"
  },
  "url": "https://paper.people.com.cn/rmrb/pc/content/202601/20/content_30133983.html"
}
```

**Features:**
- Extracts full article content from `#articleContent`
- Extracts title, navigation links (previous/next article)
- Parses date info from the newspaper reference: `《人民日报》（2026年01月20日 第 11 版）`

### 2. get_layout

Fetches a layout page, which lists all articles on a specific page of the newspaper.

**Parameters:**
- `url` (required): The full URL of the layout page

**Returns:**
```json
{
  "page_info": {
    "page_number": "11",
    "page_section": "文化",
    "date": "2026-01-20"
  },
  "articles": [
    {
      "title": "展楚韵瑰宝 览雅乐风采（感知文化里的中国）",
      "url": "https://paper.people.com.cn/rmrb/pc/content/202601/20/content_30133980.html"
    }
  ],
  "page_navigation": [
    {
      "page_number": 1,
      "text": "第01版：要闻",
      "url": "https://paper.people.com.cn/rmrb/pc/layout/202601/20/node_01.html"
    }
  ],
  "url": "http://paper.people.com.cn/rmrb/pc/layout/202601/20/node_11.html"
}
```

### 3. get_index

Fetches the main index page showing today's edition information.

**Parameters:** None required

**Returns:**
```json
{
  "current_date": "2026-06-21",
  "pages": [
    {
      "page_number": 1,
      "section": "要闻",
      "text": "第01版 要闻",
      "url": "http://paper.people.com.cn/rmrb/pc/layout/202606/21/node_01.html"
    }
  ],
  "pdf_url": null,
  "url": "http://paper.people.com.cn/rmrb/pc/layout/index.html"
}
```

### 4. search_by_date

Retrieves articles from a specific date and page.

**Parameters:**
- `date` (required): Date in YYYY-MM-DD format (e.g., "2026-01-20")
- `page` (optional): Page number (1-20), defaults to 1

**Returns:** Same structure as `get_layout`

## Usage Examples

### Fetch an article by URL
```python
result = await execute({
    "function": "get_article",
    "url": "https://paper.people.com.cn/rmrb/pc/content/202601/20/content_30133983.html"
})
print(result['title'])  # 神舟二十号飞船安全顺利返回东风着陆场
print(result['content'])  # Full article text
```

### Browse a specific page
```python
result = await execute({
    "function": "get_layout",
    "url": "http://paper.people.com.cn/rmrb/pc/layout/202601/20/node_11.html"
})
for article in result['articles']:
    print(article['title'])
```

### Search by date
```python
result = await execute({
    "function": "search_by_date",
    "date": "2026-01-20",
    "page": 11
})
print(result['page_info'])  # {'page_number': '11', 'page_section': '文化', 'date': '2026-01-20'}
```

### Get today's index
```python
result = await execute({
    "function": "get_index"
})
print(f"Today's date: {result['current_date']}")
for page in result['pages']:
    print(f"Page {page['page_number']}: {page['section']}")
```

### Navigate between articles
```python
# First get an article
article = await execute({
    "function": "get_article",
    "url": "https://paper.people.com.cn/rmrb/pc/content/202601/20/content_30133983.html"
})

# Get the next article
if article['navigation'].get('next'):
    next_article = await execute({
        "function": "get_article",
        "url": article['navigation']['next']
    })
```

## Notes

- The site uses static HTML pages, no JavaScript rendering required
- Article content is extracted from the `#articleContent` element
- Common page sections: 要闻, 评论, 经济, 理论, 政治, 文化, 社会, 生态, 体育, 国际, 党建, 副刊
- Date extraction works from URL patterns (YYYYMM/DD format)
- Error handling returns structured error objects instead of raising exceptions