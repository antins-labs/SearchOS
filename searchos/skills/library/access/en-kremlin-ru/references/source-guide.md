# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Kremlin Press Releases Access Skill

This skill provides structured access to official press releases, transcripts, and documents from the Kremlin website (en.kremlin.ru).

## Features

### Get Press Release
Retrieve detailed information about a specific press release by ID or URL.

**Parameters:**
- `news_id` (string): The numeric ID from the Kremlin URL (e.g., "69922")
- `url` (string): Full URL or relative path to the press release

**Returns:**
- Title
- Date (formatted and ISO format)
- Time
- Location
- Lead/summary paragraph
- Full content (structured as paragraphs, headings, lists, quotes)
- Tags/categories
- Photo count
- Link to Russian version

**Example:**
```json
{
  "function": "get_press_release",
  "news_id": "69922"
}
```

### List Press Releases
Browse press releases with pagination.

**Parameters:**
- `page` (integer): Page number (default: 1)
- `category` (string): Content category (default: "president/news")
  - `president/news` - Presidential news
  - `president/transcripts` - Transcripts of speeches
  - `president/appearances` - Public appearances
  - `president/letters` - Official letters
  - `president/executives` - Executive orders

**Returns:**
- List of items with title, URL, date, and tags
- Current page number
- Whether more pages are available

**Example:**
```json
{
  "function": "list_press_releases",
  "page": 1,
  "category": "president/news"
}
```

### Search Press Releases
Search for press releases by keyword.

**Parameters:**
- `query` (string): Search terms
- `page` (integer): Page number (default: 1)

**Returns:**
- Matching items with title, URL, date, and snippet
- Current page number

**Example:**
```json
{
  "function": "search_press_releases",
  "query": "CSTO summit"
}
```

## Data Structure

### Press Release Object
```json
{
  "url": "http://en.kremlin.ru/events/president/news/69922",
  "title": "CSTO summit",
  "date": "November 23, 2022",
  "date_iso": "2022-11-23",
  "time": "19:20",
  "location": "Yerevan",
  "lead": "The President of Russia took part in...",
  "content": [
    {"type": "paragraph", "text": "..."},
    {"type": "heading", "text": "...", "level": 2},
    {"type": "list", "items": ["...", "..."], "ordered": false}
  ],
  "content_text": "Full plain text content...",
  "tags": ["international", "security"],
  "photos_count": 5,
  "russian_version_url": "http://kremlin.ru/events/president/news/69922"
}
```

### News Item Object (for lists)
```json
{
  "title": "Meeting with Governor...",
  "url": "http://en.kremlin.ru/events/president/news/80320",
  "date": "July 21, 2026",
  "date_iso": "2026-07-21",
  "location": "The Kremlin, Moscow",
  "tags": ["domestic", "governors"]
}
```

## Notes

- The Kremlin website provides both English (en.kremlin.ru) and Russian (kremlin.ru) versions
- Content is typically structured with clear metadata including date, time, and location
- Press releases often include lists of participants, signed documents, and photo galleries
- Historical content dates back to the early 2000s
