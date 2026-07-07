# Tencent News (news.qq.com) Access Skill

This skill extracts complete article content and comments from Tencent News (腾讯新闻) articles at news.qq.com.

## Features

- **Full Article Extraction**: Reliably extracts article title, author, publish time, source, and full content text
- **Structured Content**: Properly handles structured content like lists, tables, and formatted text that generic readers often miss
- **Comments**: Fetches user comments with author, content, and like counts
- **URL Flexibility**: Accepts either a full URL or just the article ID

## Why This Skill?

The generic reader may fail to fully extract structured content from Tencent News pages. For example, an article listing "Ma Long's 31 World Championship Titles" with detailed breakdowns of Olympic, World Championship, and World Cup victories might yield incomplete results. This skill specifically targets the Tencent News page structure to reliably extract all content.

## Functions

### fetch_article

Extracts article content only.

**Parameters:**
- `article_id` or `url` (required): Article ID (e.g., "20240809A0A61900") or full URL

**Returns:**
- `title`: Article title
- `source`: Source/media name (e.g., "懂球帝")
- `author`: Article author
- `publish_time`: Publication timestamp
- `description`: Article description/summary
- `content`: Full article text content
- `cover_image`: Cover image URL (if available)
- `content_length`: Character count of extracted content

### fetch_comments

Fetches comments on an article.

**Parameters:**
- `article_id` or `url` (required): Article ID or full URL
- `req_num` (optional): Number of comments to fetch (default: 20)

**Returns:**
- `total_count`: Total number of comments
- `comments`: List of comment objects with:
  - `id`: Comment ID
  - `content`: Comment text
  - `author`: Author name
  - `agree_count`: Number of likes
  - `time`: Comment timestamp

### fetch_full_article

Combines article content and comments in one call.

**Parameters:**
- `article_id` or `url` (required): Article ID or full URL

**Returns:**
All fields from `fetch_article` plus:
- `total_comments`: Total comment count
- `comments`: List of comments

## Article ID Format

Tencent News article IDs follow the pattern: `YYYYMMDDAXXXXXXX`
- 8 digits for date (YYYYMMDD)
- Letter 'A'
- 7 digits for sequence

Example: `20240809A0A61900`

URLs are typically in the format:
`https://news.qq.com/rain/a/{article_id}`

## Example Usage

```json
// Fetch article by URL
{
  "function": "fetch_article",
  "url": "https://news.qq.com/rain/a/20240809A0A61900"
}

// Fetch article by ID
{
  "function": "fetch_article",
  "article_id": "20240809A0A61900"
}

// Fetch comments
{
  "function": "fetch_comments",
  "article_id": "20240809A0A61900",
  "req_num": 50
}

// Fetch everything
{
  "function": "fetch_full_article",
  "url": "https://news.qq.com/rain/a/20240809A0A61900"
}
```

## Technical Details

- Uses BeautifulSoup for HTML parsing
- Extracts content from `comps-contentify-wrap` div which contains the main article body
- Retrieves metadata from Open Graph tags and internal meta elements
- Comments fetched via Tencent's internal API at `i.news.qq.com/getQQNewsComment`

## Limitations

- Only works with public articles, may not work with member-only content
- Comment API may have rate limits
- Some dynamic content loaded via JavaScript after initial page load may not be captured