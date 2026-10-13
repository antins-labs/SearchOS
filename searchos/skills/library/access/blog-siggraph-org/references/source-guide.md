# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# SIGGRAPH Blog Access Skill

This skill fetches and parses award winner information from the ACM SIGGRAPH Blog (blog.siggraph.org).

## Features

### 1. Get Award Winners (`get_award_winners`)

Retrieves comprehensive award winner lists from SIGGRAPH conference blog posts, including:

- **Art Gallery**: Best in Show
- **Art Papers**: Best Art Paper
- **Electronic Theater**: Best in Show, Jury's Choice, Best Student Project, Audience Choice
- **Emerging Technologies**: Best in Show, Audience Choice
- **Immersive Pavilion**: Best in Show
- **Real-Time Live!**: Best in Show, Audience Choice
- **Technical Papers**: Best in Show (summary)
- **VR Theater**: Best in Show
- **Test-of-Time Awards**

Each award entry includes:
- Award category
- Project/work title
- Authors/creators
- Related links (videos, podcasts, articles)

**Example:**
```python
params = {
    "function": "get_award_winners",
    "year": "2024"
}
```

Or with a specific URL:
```python
params = {
    "function": "get_award_winners",
    "url": "https://blog.siggraph.org/2024/08/celebrating-excellence-siggraph-2024-award-winners.html/"
}
```

### 2. Get Technical Papers (`get_technical_papers`)

Retrieves detailed technical paper awards including:

- **Best Papers**: Top research papers with titles, authors, and descriptions
- **Honorable Mentions**: Notable papers deserving recognition
- **Test-of-Time Awards**: Influential papers from 10+ years ago

Each paper entry includes:
- Paper title
- Authors
- Brief description (when available)
- Links to the papers

**Example:**
```python
params = {
    "function": "get_technical_papers",
    "year": "2024"
}
```

### 3. Search Posts (`search_posts`)

Search the SIGGRAPH blog for relevant posts.

**Example:**
```python
params = {
    "function": "search_posts",
    "query": "technical papers 2024"
}
```

## Output Format

### Award Winners Response
```json
{
  "page_title": "Celebrating Excellence: SIGGRAPH 2024 Award Winners",
  "awards": [
    {
      "category": "Best in Show: Art Gallery",
      "title": "Rage Against the Archive",
      "authors": "Anshul Roy, Syracuse University",
      "links": [...],
      "raw_text": "..."
    }
  ],
  "total_awards": 25,
  "url": "...",
  "status": 200
}
```

### Technical Papers Response
```json
{
  "page_title": "SIGGRAPH 2024 Technical Papers Awards...",
  "papers": {
    "best_papers": [...],
    "honorable_mentions": [...],
    "test_of_time": [...]
  },
  "total_best_papers": 5,
  "total_honorable_mentions": 12,
  "total_test_of_time": 4,
  "url": "...",
  "status": 200
}
```

## Notes

- The blog uses the Divi theme, which renders content dynamically but returns full HTML in HTTP responses
- Direct HTTP requests are sufficient; no browser automation needed
- The skill handles nested list structures common in the blog's award formatting
- Default URLs are constructed based on the year parameter
- If a specific URL is provided, it overrides the default URL construction

## Common URLs

- **Award Winners (2024)**: https://blog.siggraph.org/2024/08/celebrating-excellence-siggraph-2024-award-winners.html/
- **Technical Papers (2024)**: https://blog.siggraph.org/2024/06/siggraph-2024-technical-papers-awards-best-papers-honorable-mentions-and-test-of-time.html/
