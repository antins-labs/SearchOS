# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Google Scholar Author Profile Access Skill

This skill fetches author profile data from Google Scholar (scholar.google.com).

## Features

- **Author Information**: Name, affiliation, and research interests
- **Citation Statistics**: Total citations, h-index, i10-index (all-time and since 2019)
- **Publications List**: Title, authors, venue, year, and citation count for each paper
- **Co-authors**: List of frequent collaborators

## Usage

### Get Complete Author Profile

```json
{
  "function": "get_author_profile",
  "user_id": "loPoqyy0AAAAJ"
}
```

### Get Publications Only

```json
{
  "function": "get_publications",
  "user_id": "loPoqyy0AAAAJ",
  "max_publications": 50
}
```

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `function` | Yes | `get_author_profile` or `get_publications` |
| `user_id` | Yes | Google Scholar user ID from the profile URL |
| `max_publications` | No | Maximum number of publications to return (default: 100) |

## Finding the User ID

The user ID is the `user` parameter in a Google Scholar profile URL:

```
https://scholar.google.com/citations?user=loPoqyy0AAAAJ
                                    ^^^^^^^^^^^^^^
                                    This is the user_id
```

## Response Structure

### Success Response

```json
{
  "status": "success",
  "user_id": "loPoqyy0AAAAJ",
  "author_name": "Author Name",
  "affiliation": "University / Institution",
  "research_interests": ["Machine Learning", "AI"],
  "statistics": {
    "total_citations": "12345",
    "citations_since_2019": "6789",
    "h_index": "45",
    "h_index_since_2019": "32",
    "i10_index": "89",
    "i10_index_since_2019": "67"
  },
  "publications": [
    {
      "title": "Publication Title",
      "authors": "Author1, Author2, Author3",
      "venue": "Journal Name, 2020",
      "year": "2020",
      "citations": "1234",
      "link": "https://scholar.google.com/..."
    }
  ],
  "coauthors": ["Co-author 1", "Co-author 2"]
}
```

### Error Response

```json
{
  "status": "blocked",
  "error": "Google Scholar blocked the request (403 Forbidden)",
  "message": "Google Scholar detected automated access..."
}
```

## Important Notes

### Access Restrictions

Google Scholar actively blocks automated access. This skill implements multiple strategies to access the data, but you may encounter:

- **403 Forbidden**: Google detected automated access
- **Sign-in Required**: Profile requires authentication
- **Rate Limiting**: Too many requests from the same IP

If blocked, wait some time before retrying or try from a different network.

### Data Availability

Not all profiles have all data fields. Some authors may have:
- Hidden citation statistics
- Limited publication lists
- No co-author information

### Rate Limiting

Google Scholar has strict rate limits. Avoid making many requests in quick succession.

## Technical Details

The skill uses Playwright browser automation with:
- Multiple user agent strategies (Safari, Chrome)
- Anti-detection measures (webdriver hiding)
- Automatic handling of sign-in prompts
- Dynamic content loading for publication lists

## Limitations

1. **No Authentication**: Cannot access private profiles or authenticated features
2. **No Search**: Only works with known user IDs, cannot search for authors
3. **Rate Limited**: Google may block requests if accessed too frequently
4. **Dynamic Content**: Some data may require JavaScript rendering
