# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Apple Fandom Wiki Access Skill

Access structured information from the Apple Fandom wiki (apple.fandom.com), a community-maintained encyclopedia covering Apple products, people, history, and related topics.

## Overview

This skill uses the MediaWiki API to retrieve clean, structured data from the Apple Fandom wiki, bypassing the ads and navigation clutter that make web scraping difficult. It extracts:

- **Page content** with sections, paragraphs, and lists
- **Infobox data** from wiki templates (person info, product specs, etc.)
- **Search results** with snippets and metadata
- **Category listings** for browsing related pages

## Functions

### get_page

Retrieve detailed information about a specific wiki page.

```python
# Get information about Steve Jobs
result = await execute({
    "function": "get_page",
    "page_title": "Steve_Jobs"
})

# Returns:
{
    "title": "Steve Jobs",
    "url": "https://apple.fandom.com/wiki/Steve_Jobs",
    "page_id": 1234,
    "sections": [
        {"name": "Early life", "level": 2},
        {"name": "Career", "level": 2},
        ...
    ],
    "infobox": {
        "birth name": "Steven Paul Jobs",
        "born": "February 24, 1955, San Francisco, California",
        "died": "October 5, 2011 (aged 56), Palo Alto, California",
        ...
    },
    "content": {
        "paragraphs": [...],
        "sections": {
            "intro": [...],
            "Early life": [...],
            ...
        }
    },
    "categories": ["Former_Apple_employees", ...],
    "links": ["Apple", "Macintosh", ...]
}
```

**Parameters:**
- `page_title` (required): Wiki page title (underscores for spaces)
- `include_content` (optional, default: true): Include parsed content
- `include_wikitext` (optional, default: false): Include raw wikitext source

### search

Search for wiki pages matching a query.

```python
# Search for iPhone-related pages
result = await execute({
    "function": "search",
    "query": "iPhone",
    "limit": 10
})

# Returns:
{
    "query": "iPhone",
    "total_hits": 150,
    "results": [
        {
            "title": "IPhone (1st generation)",
            "url": "https://apple.fandom.com/wiki/IPhone_(1st_generation)",
            "snippet": "...",
            "word_count": 2275
        },
        ...
    ]
}
```

**Parameters:**
- `query` (required): Search query string
- `limit` (optional, default: 10): Max results (1-50)

### get_category

List pages in a category.

```python
# Get pages in the Former Apple Employees category
result = await execute({
    "function": "get_category",
    "category_name": "Former_Apple_employees",
    "limit": 20
})

# Returns:
{
    "category": "Category:Former_Apple_employees",
    "members": [
        {"title": "Steve Jobs", "type": "page"},
        {"title": "John Sculley", "type": "page"},
        ...
    ],
    "continue_token": "..."  # For pagination
}
```

**Parameters:**
- `category_name` (required): Category name (with or without "Category:" prefix)
- `limit` (optional, default: 20): Max results (1-50)
- `continue_token` (optional): Token from previous response for pagination

### get_random

Get random pages from the wiki.

```python
result = await execute({
    "function": "get_random",
    "limit": 5
})
```

**Parameters:**
- `limit` (optional, default: 5): Number of random pages (1-20)
- `namespace` (optional, default: 0): Namespace ID (0 = articles)

## Use Cases

- **Research Apple history**: Get information about key figures like Steve Jobs, John Sculley, Jony Ive
- **Product information**: Look up details about iPhone models, Macintosh computers, iPods
- **Browse related content**: Use categories to find related pages
- **Search functionality**: Find pages matching specific keywords

## Notes

- Page titles use underscores for spaces (e.g., `Steve_Jobs` not `Steve Jobs`)
- The skill bypasses Cloudflare protection and ad clutter by using the MediaWiki API directly
- Infobox extraction works best for pages using standard templates (Person, Apple Infobox, etc.)
- Categories are returned without the "Category:" prefix in titles but include it in the response
