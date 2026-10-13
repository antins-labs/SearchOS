# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# TheSecondWorldWar.org Access Skill

This skill retrieves structured historical articles about World War II from [thesecondworldwar.org](https://www.thesecondworldwar.org).

## Overview

The website hosts detailed, well-researched articles about various aspects of World War II, including:
- The Axis Powers (Germany, Italy, Japan, and their allies)
- The Allied Powers
- Military campaigns and battles
- Political developments
- Home front experiences
- Interwar period (1918-1936)

## Functions

### get_article

Fetches a single article with full content extraction.

**Parameters:**
- `url` (required): URL path to the article
  - Example: `/the-axis-powers/state-of-burma`

**Returns:**
- `title`: Article title
- `breadcrumbs`: Navigation path
- `content`: 
  - `paragraphs`: List of all text paragraphs
  - `paragraph_count`: Number of paragraphs
  - `total_text_length`: Total character count
- `images`: List of images with src and alt text
- `related_links`: Internal links to related articles
- `headings`: Document structure with heading levels

**Example:**
```python
{
    "function": "get_article",
    "url": "/the-axis-powers/state-of-burma"
}
```

### get_category

Fetches a category/section page with article listings.

**Parameters:**
- `url` (required): URL path to the category
  - Example: `/the-axis-powers/`

**Returns:**
- `title`: Category title
- `breadcrumbs`: Navigation path
- `description`: Introduction paragraphs for the category
- `articles`: List of articles in this category with titles and URLs
- `article_count`: Number of articles found
- `headings`: Section headings within the page

**Example:**
```python
{
    "function": "get_category",
    "url": "/the-axis-powers/"
}
```

### search_articles

Searches for articles by keyword in titles within a category.

**Parameters:**
- `query` (required): Search keyword
- `category` (optional): Category path to search within (default: `/`)
- `max_results` (optional): Maximum results to return (default: 20)

**Returns:**
- `query`: The search term used
- `category`: The category searched
- `results`: List of matching articles with titles and URLs
- `result_count`: Number of results found

**Example:**
```python
{
    "function": "search_articles",
    "query": "Germany",
    "category": "/the-axis-powers/",
    "max_results": 10
}
```

### get_breadcrumbs

Gets the navigation breadcrumb path for a page.

**Parameters:**
- `url` (required): URL path to the page

**Returns:**
- `breadcrumbs`: Hierarchical navigation path
- `main_navigation`: Main site navigation links

**Example:**
```python
{
    "function": "get_breadcrumbs",
    "url": "/the-axis-powers/germany-2"
}
```

## Site Structure

The website is organized hierarchically:

```
/ (Home)
├── /interbellum-1918-1936/ (Interwar Period)
│   ├── /1918/
│   ├── /1919/
│   └── ...
├── /the-axis-powers/ (Axis Powers)
│   ├── /germany-2 (Nazi Germany)
│   ├── /italy-3 (Kingdom of Italy)
│   ├── /japan-1 (Empire of Japan)
│   ├── /state-of-burma
│   └── ...
├── /eastern-front/ (Eastern Front)
├── /a-second-front/ (Western Front)
├── /home-front/ (Home Front)
└── ...
```

## Content Format

Articles are structured historical essays with:
- Clear titles and hierarchical navigation
- Well-organized paragraphs with substantial content
- Related article links for deeper exploration
- Occasional images from the period

## Notes

- All URLs should be provided as paths starting with `/` (e.g., `/the-axis-powers/germany-2`)
- The skill automatically normalizes URLs and handles both with and without trailing slashes
- Content is extracted from the main content area, filtering out navigation and footer elements
- Related links are limited to internal site links only
