# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Top Conference Best Papers

Extracts award-winning papers from top AI/ML conferences from the GitHub repository [FeijiangHan/Top-Conference-Best-Papers](https://github.com/FeijiangHan/Top-Conference-Best-Papers).

## Supported Conferences

- **Machine Learning**: ICLR, NeurIPS, ICML
- **Computer Vision**: CVPR, ICCV, ECCV
- **Artificial Intelligence**: AAAI

## Functions

### list_papers

List all best papers with optional filtering by venue, year, category, title, or author.

**Parameters:**
- `venue` (optional): Filter by conference name (e.g., "ICLR", "NeurIPS", "CVPR")
- `year` (optional): Filter by year (e.g., "2024", "2025")
- `category` (optional): Filter by award category (partial match, e.g., "Outstanding Paper", "Test of Time")
- `conference` (optional): Filter by conference section
- `title` (optional): Filter by title keyword
- `author` (optional): Filter by author name
- `limit` (optional): Maximum number of results (default: 50)

**Example:**
```json
{
  "function": "list_papers",
  "venue": "ICLR",
  "year": "2025"
}
```

### get_venues

Get list of all venues (conferences) with paper counts.

**Example:**
```json
{
  "function": "get_venues"
}
```

### get_years

Get list of all years with paper counts.

**Example:**
```json
{
  "function": "get_years"
}
```

### get_categories

Get list of all award categories with paper counts.

**Example:**
```json
{
  "function": "get_categories"
}
```

### search_papers

Search papers by title or author keyword.

**Parameters:**
- `query` (required): Search keyword (searches in title and authors)
- `limit` (optional): Maximum number of results (default: 20)

**Example:**
```json
{
  "function": "search_papers",
  "query": "transformer"
}
```

## Return Format

All functions return a JSON object with the following structure:

```json
{
  "success": true,
  "total": 299,
  "returned": 50,
  "papers": [
    {
      "title": "Paper Title",
      "venue": "ICLR",
      "year": "2025",
      "authors": "Author 1, Author 2",
      "conference_section": "ICLR",
      "category": "Outstanding Papers 2025",
      "paper_url": "https://openreview.net/...",
      "code_url": "https://github.com/..."
    }
  ]
}
```

## Award Categories

The repository tracks various award types including:
- Outstanding Paper Awards
- Best Paper Awards
- Test of Time Awards
- Best Student Paper Awards
- Honorable Mentions
- And many more conference-specific awards

## Data Freshness

The data is fetched live from the GitHub repository, ensuring access to the most up-to-date information on award-winning papers.
