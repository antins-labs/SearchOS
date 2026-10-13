# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Azerbaijan Ministry of Foreign Affairs (MFA) Access Skill

This skill extracts news articles and bilateral relations information from the official website of the Ministry of Foreign Affairs of the Republic of Azerbaijan (www.mfa.gov.az).

## Features

### 1. Get News Article (`get_news_article`)

Extract a specific news article by URL.

**Parameters:**
- `url` (required): Full URL to the news article

**Example:**
```
url: https://www.mfa.gov.az/en/news/no28022
```

**Returns:**
- Article title, date, category
- Full text content
- Images (if any)
- Article ID

### 2. List News (`list_news`)

List news articles with pagination support.

**Parameters:**
- `page` (optional): Page number (default: 1)
- `lang` (optional): Language code - 'en' for English, 'az' for Azerbaijani (default: 'en')

**Returns:**
- List of articles with title, date, category, and URL
- Pagination info (current page, total pages)

### 3. Get Bilateral Relations (`get_bilateral_relations`)

Extract bilateral relations information for a specific country.

**Parameters:**
- `url` (optional): Full URL to the bilateral relations page
- `region` (optional): Region name (e.g., 'africa', 'asia', 'europe')
- `country` (optional): Country slug (e.g., 'chad', 'pakistan')
- `lang` (optional): Language code (default: 'en')

Note: Either `url` OR both `region` and `country` must be provided.

**Example URLs:**
- Africa/Chad: https://www.mfa.gov.az/en/category/africa/chad
- Asia/Pakistan: https://www.mfa.gov.az/en/category/asia/pakistan
- Europe/Germany: https://www.mfa.gov.az/en/category/europe/germany

**Returns:**
- Country name and region
- Full content about diplomatic relations
- Structured sections (visits, agreements, cooperation, etc.)

## Site Structure Notes

The MFA Azerbaijan website has two main content types:

1. **News Articles** (`/en/news/...`)
   - Title in `.section_articleInner_body_head--header`
   - Content in `.section_articleInner_body_content--description`
   - Date typically in first paragraph
   - Images in `.section_articleInner_body`

2. **Bilateral Relations** (`/en/category/{region}/{country}`)
   - Content in `.page_content`
   - Contains diplomatic relations history
   - Information about embassies, visits, agreements

## Language Support

The site supports:
- English (`/en/`)
- Azerbaijani (`/az/`)

Use the `lang` parameter to specify the language for news listings.
