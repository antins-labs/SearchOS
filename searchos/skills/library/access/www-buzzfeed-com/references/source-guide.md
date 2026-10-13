# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# BuzzFeed Access Skill

Extract structured content from BuzzFeed articles, including checklist items, quiz results, and article metadata.

## Features

This skill parses the embedded `__NEXT_DATA__` JSON in BuzzFeed pages to extract structured data that's difficult to obtain through generic readers:

- **Checklist Extraction**: Get all items from checklist-style quizzes (e.g., "How many of these TV shows have you seen?")
- **Quiz Results**: Extract personality quiz result options
- **Article Metadata**: Title, author, publish date, tags, and more

## Functions

### `get_article`

Fetch article metadata from a BuzzFeed URL.

**Parameters:**
- `url` (required): The BuzzFeed article URL

**Returns:**
```json
{
  "success": true,
  "id": "4646992",
  "title": "If You've Seen 25/100 Of IMDb's Top Rated TV Shows You're A TV Buff",
  "description": "Are you a TV fanatic?",
  "author": "Hattie Soykan",
  "author_url": "https://twitter.com/hattiesoykan",
  "published": "2017-10-06T10:13:40Z",
  "category": "UK",
  "language": "en",
  "country": "en-uk",
  "canonical_url": "https://www.buzzfeed.com/hattiesoykan/how-many-of-imdbs-top-100-rated-tv-shows-have-you-seen",
  "tags": ["checklist", "imdb", "quiz", "tv"],
  "is_quiz": true,
  "is_checklist": true,
  "image": "https://img.buzzfeed.com/..."
}
```

### `get_checklist`

Extract checklist items from a BuzzFeed checklist/quiz article.

**Parameters:**
- `url` (required): The BuzzFeed checklist/quiz URL
- `include_metadata` (optional, default: true): Include article metadata

**Returns:**
```json
{
  "success": true,
  "item_count": 100,
  "items": [
    {
      "id": "1",
      "name": "Planet Earth II",
      "year": 2016,
      "original_text": "_Planet Earth II_ (2016)",
      "image_url": "https://img.buzzfeed.com/...",
      "image_credit": "Via BBC"
    },
    {
      "id": "2",
      "name": "Band of Brothers",
      "year": 2001,
      "original_text": "_Band of Brothers_ (2001)",
      "image_url": "https://img.buzzfeed.com/...",
      "image_credit": "Via HBO"
    }
  ],
  "article": { ... }
}
```

### `get_quiz_results`

Extract quiz result options from a BuzzFeed personality quiz.

**Parameters:**
- `url` (required): The BuzzFeed quiz URL
- `include_metadata` (optional, default: true): Include article metadata

**Returns:**
```json
{
  "success": true,
  "result_count": 5,
  "results": [
    {
      "id": "1",
      "title": "The TV Expert",
      "description": "You've seen everything!",
      "image_url": "https://img.buzzfeed.com/..."
    }
  ],
  "article": { ... }
}
```

## Example Usage

### Extract IMDb Top 100 TV Shows Checklist

```
Function: get_checklist
URL: https://www.buzzfeed.com/hattiesoykan/how-many-of-imdbs-top-100-rated-tv-shows-have-you-seen
```

Returns all 100 TV shows with their names, years, and associated images - perfect for creating your own checklist or analyzing the list.

### Get Article Metadata

```
Function: get_article
URL: https://www.buzzfeed.com/...
```

Returns basic article information without the checklist items.

## How It Works

1. Fetches the HTML page from BuzzFeed
2. Extracts the `__NEXT_DATA__` JSON embedded in the page
3. Parses the structured quiz/checklist data from the JSON
4. Returns clean, structured data with parsed names and years

## Notes

- The skill uses direct HTTP requests (no browser automation needed) for fast performance
- Checklist item text is parsed to extract names and years (e.g., "_Planet Earth II_ (2016)" → name: "Planet Earth II", year: 2016)
- Images and credits are included for each checklist item when available
- Works with most BuzzFeed quiz and checklist formats
