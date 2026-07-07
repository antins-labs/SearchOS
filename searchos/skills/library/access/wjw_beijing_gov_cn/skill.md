# Beijing Health Commission (wjw.beijing.gov.cn) Access Skill

## Overview

This skill provides structured access to the Beijing Municipal Health Commission website (北京市卫生健康委员会), enabling retrieval of official healthcare notices, hospital approvals, medical institution registrations, and regulatory documents.

## Website Background

The Beijing Health Commission website (wjw.beijing.gov.cn) is the official portal for healthcare-related government information in Beijing. Key content includes:

- **Hospital and Medical Institution Approvals**: Official approvals for new medical facilities, technology adoptions, and regulatory compliance
- **Assisted Reproductive Technology Approvals**: Authorizations and inspections for IVF clinics and related services
- **Professional Licensing**: Physician registrations, assessments, and credentialing notices
- **Healthcare Policy Announcements**: New regulations, guidelines, and policy implementations
- **Medical Quality Control Reports**: Assessments and evaluations of medical institutions

## Functions

### 1. Get Article

Retrieve a single article with full content and metadata.

**Parameters:**
- `url` (required): Article URL or path

**Example:**
```python
result = await execute({
    'function': 'get_article',
    'url': 'https://wjw.beijing.gov.cn/zwgk_20040/ylws/202308/t20230802_3212648.html'
})
```

**Returns:**
```json
{
    "success": true,
    "url": "https://wjw.beijing.gov.cn/...",
    "title": "北京市卫生健康委员会关于...",
    "pub_date": "2023-07-27 10:45",
    "source": "北京市卫生健康委员会",
    "category": "医疗卫生",
    "content": "北京家恩德运医院：...",
    "content_length": 327,
    "doc_id": "3212648"
}
```

### 2. List Articles

Browse articles from a specific category with pagination.

**Parameters:**
- `category` (optional, default: 'ylws'): Category code
- `page` (optional, default: 1): Page number

**Available Categories:**
| Code | Chinese Name | English Translation |
|------|-------------|---------------------|
| ylws | 医疗卫生 | Medical Health |
| zwgk | 政务公开 | Government Information |
| fgwj | 法规文件 | Regulations and Documents |
| gzdt | 工作动态 | Work Dynamics |

**Example:**
```python
result = await execute({
    'function': 'list_articles',
    'category': 'ylws',
    'page': 1
})
```

**Returns:**
```json
{
    "success": true,
    "category": "ylws",
    "category_name": "医疗卫生 (Medical Health)",
    "page": 1,
    "count": 24,
    "has_next": true,
    "articles": [
        {
            "title": "北京市卫生健康委员会关于...",
            "url": "https://wjw.beijing.gov.cn/...",
            "date": "2023-08-01"
        }
    ]
}
```

### 3. Search by Keyword

Search for articles by keyword across multiple pages.

**Parameters:**
- `keyword` (required): Search term (min 2 characters)
- `category` (optional, default: 'ylws'): Category to search
- `max_pages` (optional, default: 3, max: 10): Pages to search

**Example:**
```python
result = await execute({
    'function': 'search_by_keyword',
    'keyword': '医院',
    'category': 'ylws',
    'max_pages': 5
})
```

### 4. Get Batch Articles

Fetch multiple articles at once.

**Parameters:**
- `urls` (required): List of URLs (max 10)

**Example:**
```python
result = await execute({
    'function': 'get_batch_articles',
    'urls': [
        'https://wjw.beijing.gov.cn/zwgk_20040/ylws/202308/t20230802_3212648.html',
        'https://wjw.beijing.gov.cn/zwgk_20040/ylws/202107/t20210728_2449992.html'
    ]
})
```

## Content Types

The website contains the following types of official documents:

1. **医疗机构审批 (Medical Institution Approvals)**
   - New hospital registrations
   - Facility expansions
   - Service additions

2. **人类辅助生殖技术 (Assisted Reproductive Technology)**
   - IVF clinic approvals
   - Technology inspection results
   - Compliance assessments

3. **执业注册通知 (Professional Registration Notices)**
   - Physician licensing
   - Nurse registrations
   - Medical professional assessments

4. **医疗质量控制 (Medical Quality Control)**
   - Hospital quality evaluations
   - Specialty department assessments
   - Safety inspections

## Technical Details

### URL Patterns

- **Article URL**: `/zwgk_20040/{category}/{year}/{month}/t{date}_{id}.html`
- **List URL**: `/zwgk_20040/{category}/index.html` (page 1)
- **Paginated List**: `/zwgk_20040/{category}/index_{n}.html` (page n)

### Metadata Extraction

The skill extracts the following metadata from meta tags:
- `ArticleTitle`: Document title
- `PubDate`: Publication date and time
- `ContentSource`: Source department
- `ColumnName`: Category name
- `Keywords`: Document keywords

### Content Extraction

Article content is extracted from the `.view` container element, which holds the main document body in Chinese government CMS templates.

## Data Quality Notes

### Why This Skill is Needed

The generic SearchOS reader failed to access this site due to:

1. **Government CMS Structure**: Uses standardized Chinese government portal template that differs from typical news sites
2. ** Specific Content Selectors**: Requires targeting `.view` class and specific meta tags
3. **Encoding**: UTF-8 content with Chinese characters requires proper handling
4. **Pagination Pattern**: Uses index_{n}.html convention common in Chinese government portals

### Verified Content

Based on probe URLs tested:
- Article titles ✓ Extracted successfully
- Publication dates ✓ Available in meta tags and list pages
- Full article content ✓ Extracted from `.view` element
- Article lists ✓ Paginated browsing works

## Rate Limiting

To avoid overloading the government server:
- Maximum 2 requests per second
- Maximum 10 concurrent connections
- 30-second timeout per request

## Examples

### Find Hospital Approval Notices

```python
# Search for hospital-related notices
result = await execute({
    'function': 'search_by_keyword',
    'keyword': '医院',
    'category': 'ylws',
    'max_pages': 3
})

for article in result['matches']:
    print(f"{article['date']}: {article['title']}")
```

### Get ART (Assisted Reproductive Technology) Approvals

```python
# Search for ART approvals
result = await execute({
    'function': 'search_by_keyword',
    'keyword': '辅助生殖',
    'category': 'ylws'
})

# Get full content of each match
if result['success']:
    urls = [a['url'] for a in result['matches'][:5]]
    batch_result = await execute({
        'function': 'get_batch_articles',
        'urls': urls
    })
    
    for article in batch_result['articles']:
        if article.get('success'):
            print(f"\n{article['title']}")
            print(f"Published: {article['pub_date']}")
            print(article['content'][:200] + '...')
```

### Browse Latest Healthcare Notices

```python
# Get latest notices
result = await execute({
    'function': 'list_articles',
    'category': 'ylws',
    'page': 1
})

print(f"Latest {result['count']} healthcare notices:")
for i, article in enumerate(result['articles'][:10], 1):
    print(f"{i}. [{article['date']}] {article['title'][:40]}...")
```

## Error Handling

The skill returns structured error responses instead of raising exceptions:

```json
{
    "success": false,
    "error": "HTTP 408: Request timeout",
    "url": "https://wjw.beijing.gov.cn/..."
}
```

Common errors:
- **HTTP 408**: Request timeout (server slow during Chinese business hours)
- **HTTP 404**: Article not found or moved
- **HTTP 403**: Access blocked (may need different headers or delay)
- **Invalid URL**: Malformed article URL

## Dependencies

- `httpx`: Async HTTP client
- `beautifulsoup4`: HTML parsing
- No browser automation required (direct HTTP requests work)