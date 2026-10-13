# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# History.com Access Skill

This skill retrieves structured content from the History.com website, including articles, topic listings, and "This Day in History" events.

## Features

### get_article
Fetches a complete article with:
- Title and description
- Author information
- Publication and modification dates
- Article section/category
- Full article body (paragraphs)
- Subheadings

**Example:**
```python
params = {
    "function": "get_article",
    "url": "https://www.history.com/articles/burma-campaign-wwii-road-china"
}
```

### get_topic
Retrieves articles and resources for a specific topic:
- Topic name and description
- List of articles in the topic
- Related topics
- Associated videos (from JSON-LD)

**Example:**
```python
params = {
    "function": "get_topic",
    "url": "https://www.history.com/topics/world-war-ii"
}
```

### get_this_day
Extracts events from "This Day in History" pages:
- Date being highlighted
- Main event/headline
- Historical events that occurred on this day
- Notable births

**Example:**
```python
params = {
    "function": "get_this_day",
    "url": "https://www.history.com/this-day-in-history/july-22"
}
```

### get_topics_list
Gets a complete list of all topic categories available on History.com:
- Topic names and URLs
- Show names and URLs

**Example:**
```python
params = {
    "function": "get_topics_list"
}
```

## Technical Details

- Uses direct HTTP requests with proper headers
- No JavaScript rendering required
- Parses HTML with BeautifulSoup
- Extracts structured data from JSON-LD schema when available
- Handles promotional content filtering automatically

## URL Requirements

- `get_article`: URL must start with `https://www.history.com/`
- `get_topic`: URL must start with `https://www.history.com/topics/`
- `get_this_day`: URL must start with `https://www.history.com/this-day-in-history/`

## Error Handling

All functions return a dictionary with an `error` key if something goes wrong:
```python
{
    "error": "HTTP 404",
    "url": "..."
}
```

## Data Sources

Content is extracted from:
1. JSON-LD structured data (Article schema, VideoObject schema)
2. HTML meta tags (description, og:title, etc.)
3. Semantic HTML elements (h1, h2, p tags)
4. Link elements for navigation and related content
