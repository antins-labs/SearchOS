# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# CMU Graphics Lab Publications Access Skill

This skill retrieves publication data from the Carnegie Mellon University Graphics Lab website at graphics.cs.cmu.edu.

## Available Functions

### `list_publications`

Lists all publications from the CMU Graphics Lab, with optional filtering by year and pagination support.

**Parameters:**
- `year` (optional): Filter publications by year (e.g., "2024", "2023")
- `limit` (optional): Maximum number of results to return
- `offset` (optional): Pagination offset (default: 0)

**Returns:**
- Array of publications with title, authors, journal/venue, year, URL, teaser image, and page_id
- Total count and pagination metadata

**Example:**
```python
# Get all publications from 2024
result = await execute({"function": "list_publications", "year": "2024"}, ctx)

# Get first 10 publications
result = await execute({"function": "list_publications", "limit": 10}, ctx)

# Paginate through results
result = await execute({"function": "list_publications", "limit": 20, "offset": 20}, ctx)
```

### `get_publication`

Retrieves detailed information about a single publication, including the full abstract and project links.

**Parameters:**
- `page_id` (optional): The WordPress page_id of the publication
- `url` (optional): The full URL of the publication page

**Note:** Either `page_id` or `url` must be provided.

**Returns:**
- Title, authors (as array), journal/venue, year, abstract, teaser image, and project links

**Example:**
```python
# Get by page_id
result = await execute({"function": "get_publication", "page_id": "2759"}, ctx)

# Get by URL
result = await execute({"function": "get_publication", "url": "https://graphics.cs.cmu.edu/?page_id=2759"}, ctx)
```

### `search_publications`

Searches publications by title or author name.

**Parameters:**
- `query`: Search query string (case-insensitive, matches against title and authors)
- `limit` (optional): Maximum number of results (default: 20)

**Returns:**
- Array of matching publications
- Total match count

**Example:**
```python
# Search by author
result = await execute({"function": "search_publications", "query": "Crane"}, ctx)

# Search by topic
result = await execute({"function": "search_publications", "query": "neural rendering"}, ctx)
```

### `get_years`

Retrieves a list of all publication years available in the database, along with publication counts per year.

**Parameters:** None

**Returns:**
- Array of years (descending order)
- Object mapping years to publication counts
- Total publication count

**Example:**
```python
result = await execute({"function": "get_years"}, ctx)
# Returns: {"years": ["2026", "2025", ...], "year_counts": {"2024": 16, ...}, "total_publications": 302}
```

## Data Structure

### Publication Summary (from list)
```json
{
  "title": "Paper Title",
  "authors": "Author One, Author Two, Author Three",
  "journal": "ACM Trans. Graph.",
  "year": "2024",
  "url": "https://graphics.cs.cmu.edu/?page_id=2759",
  "teaser_image": "https://graphics.cs.cmu.edu/wp/wp-content/uploads/...",
  "page_id": "2759"
}
```

### Publication Detail (from get_publication)
```json
{
  "title": "Paper Title",
  "authors": ["Author One", "Author Two", "Author Three"],
  "journal": "ACM Trans. Graph. (2024)",
  "year": "2024",
  "abstract": "Full abstract text...",
  "teaser_image": "https://...",
  "links": [
    {"url": "https://project-page.com", "label": "Project Page"}
  ]
}
```

## Notes

- The CMU Graphics Lab publications span from 1991 to present (302+ papers)
- Publications are primarily in computer graphics, vision, and computational photography
- The site uses WordPress; each publication has a unique page_id
- Teaser images are available for most publications
- Some publications include links to project pages, code, or supplementary materials
- The skill bypasses SSL certificate verification due to site configuration
