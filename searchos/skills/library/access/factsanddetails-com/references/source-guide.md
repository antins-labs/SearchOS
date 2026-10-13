# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Facts and Details - SearchOS Access Skill

This skill extracts structured content from [factsanddetails.com](https://factsanddetails.com), a comprehensive educational website featuring detailed articles on world history, culture, geography, and current affairs.

## Features

- **Article Extraction**: Fetches full article content with structured sections, headings, and paragraphs
- **Category Navigation**: Lists articles and subcategories from category pages
- **Region Navigation**: Lists countries and categories from region pages
- **Homepage Navigation**: Lists main regions/countries from the homepage
- **Auto-detection**: Automatically determines page type and extracts appropriate content

## Supported Functions

### get_article
Extracts structured content from an article page.

**Parameters:**
- `url` (required): The article URL (must contain `entry-` in the path)

**Returns:**
- `title`: Article title
- `sections`: Array of sections with headings and paragraphs
- `full_text`: Complete article text
- `metadata`: Description, keywords, breadcrumb path

**Example:**
```
URL: https://factsanddetails.com/southeast-asia/Laos/sub5_3a/entry-2936.html
```

### get_category
Extracts articles and subcategories from a category/subcategory page.

**Parameters:**
- `url` (required): The category page URL (contains `/sub` in path)

**Returns:**
- `title`: Category title
- `articles`: List of article titles and URLs
- `subcategories`: List of subcategory titles and URLs

**Example:**
```
URL: https://factsanddetails.com/southeast-asia/Laos/sub5_3a/
```

### get_region
Extracts countries and categories from a region page.

**Parameters:**
- `url` (required): The region page URL

**Returns:**
- `title`: Region title
- `countries`: List of country names and URLs
- `categories`: List of category titles and URLs

**Example:**
```
URL: https://factsanddetails.com/southeast-asia/
```

### get_homepage
Extracts main regions from the homepage.

**Parameters:**
- `url` (optional): Defaults to https://factsanddetails.com

**Returns:**
- `regions`: List of region names and URLs (e.g., China, Japan, Southeast Asia)

### get_page
Auto-detects page type and extracts appropriate content.

**Parameters:**
- `url` (required): Any factsanddetails.com URL

**Returns:**
- Appropriate content based on detected page type

## Site Structure

Facts and Details has a hierarchical structure:

```
Homepage
├── Regions (e.g., Southeast Asia, China, Japan)
│   ├── Countries (e.g., Laos, Thailand, Vietnam)
│   │   ├── Categories (e.g., History, People, Government)
│   │   │   └── Articles (individual content pages)
```

## Content Format

Articles are structured with:
- A main title (h1)
- Multiple sections with h3 headings
- Paragraphs of detailed content
- Metadata including description and keywords

## Notes

- The site uses semantic HTML with `<article>` tags for main content
- Articles are organized by geographic region and topic
- Content includes historical facts, cultural information, and geographical data
- The skill handles breadcrumb navigation and URL path parsing for categorization
