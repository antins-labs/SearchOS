# Baidu Baike (百度百科) Access Skill

## Overview

This skill provides access to Baidu Baike - China's largest and most comprehensive online encyclopedia. Baidu Baike contains millions of entries covering a wide range of topics including movies, TV shows, celebrities, historical figures, locations, and more.

## Key Features

- **Search**: Search for encyclopedia entries by keyword
- **Lemma Retrieval**: Extract detailed information from encyclopedia pages
- **Infobox Extraction**: Capture structured metadata from infobox tables
- **Movie Metadata**: Convenience function for extracting movie-specific fields

## Functions

### search

Search for encyclopedia entries by keyword.

**Parameters:**
- `keyword` (string, required): Search keyword (Chinese characters recommended)

**Example:**
```json
{
  "function": "search",
  "keyword": "八佰"
}
```

**Returns:**
```json
{
  "success": true,
  "keyword": "八佰",
  "redirect_url": "https://baike.baidu.com/item/%E5%85%AB%E4%BD%B0",
  "lemma_data": {
    "lemma_id": 20785278,
    "title": "八佰",
    "description": "2020年管虎执导的战争电影"
  },
  "results": [...]
}
```

### get_lemma

Retrieve detailed information about an encyclopedia entry.

**Parameters:**
- `url` (string, optional): Full URL to the lemma page
- `keyword` (string, optional): Search keyword (will search and then fetch the first result)
- `lemma_id` (string/integer, optional): Lemma ID (limited support)

**Example:**
```json
{
  "function": "get_lemma",
  "keyword": "你好，李焕英"
}
```

**Returns:**
```json
{
  "success": true,
  "title": "你好，李焕英",
  "description": "2021年贾玲执导的奇幻喜剧电影",
  "lemma_id": 20427874,
  "url": "https://baike.baidu.com/item/...",
  "summary": "《你好，李焕英》是由...",
  "infobox": {
    "中文名": "你好，李焕英",
    "外文名": "Hi, Mom",
    "类型": "奇幻、喜剧",
    "导演": "贾玲",
    "主演": "贾玲、张小斐、沈腾、陈赫",
    ...
  }
}
```

### get_movie_info

Get movie-specific information with convenience field mapping.

**Parameters:**
- `keyword` (string, optional): Movie title or search keyword
- `url` (string, optional): Full URL to the movie lemma page

**Example:**
```json
{
  "function": "get_movie_info",
  "keyword": "八佰"
}
```

**Returns:**
```json
{
  "success": true,
  "title": "八佰",
  "description": "2020年管虎执导的战争电影",
  "title_cn": "八佰",
  "title_en": "The Eight Hundred",
  "director": "管虎",
  "starring": "黄志忠、欧豪、王千源、姜武、张译、杜淳、魏晨、李晨、俞灏明",
  "release_date": "2020年8月21日",
  "box_office": "31.11 亿元",
  "runtime": "147 分钟",
  "genre": "战争",
  "production_company": "华谊兄弟电影有限公司、北京七印象文化传媒有限公司",
  "language": "普通话",
  "summary": "...",
  "infobox": {...}
}
```

## Movie Infobox Fields

Common fields extracted from movie entries:

| Chinese Field | English Mapped Field | Description |
|---------------|---------------------|-------------|
| 中文名 | title_cn | Chinese title |
| 外文名 | title_en | English/foreign title |
| 类型 | genre | Movie genre |
| 导演 | director | Director(s) |
| 编剧 | screenwriter | Screenwriter(s) |
| 制片人 | producer | Producer(s) |
| 主演 | starring | Main cast |
| 上映时间 | release_date | Release date |
| 片长 | runtime | Runtime |
| 票房 | box_office | Box office revenue |
| 出品公司 | production_company | Production company |
| 制片地区 | production_region | Production region |
| 对白语言 | language | Spoken language |
| 色彩 | color | Color/B&W |
| imdb编码 | imdb_id | IMDb ID |

## Implementation Notes

- **Browser Automation**: Uses Playwright (Chromium) due to JavaScript-rendered content
- **Infobox Parsing**: Extracts data from the basic info table via DOM scraping
- **Reference Cleanup**: Automatically removes reference markers like [53] from values
- **Error Handling**: Gracefully handles 404 errors and timeouts
- **Chinese Optimized**: Designed for Chinese-language searches

## Limitations

- Requires browser automation, which may be slower than direct API calls
- Search functionality relies on Baidu's redirect behavior
- Some entries may have incomplete infobox data
- The site may block requests that appear automated (uses realistic user agent)

## Use Cases

1. **Movie Research**: Extract comprehensive movie metadata including box office figures
2. **Cast Information**: Get detailed cast and crew information
3. **Historical Information**: Research encyclopedic entries for various topics
4. **Chinese Content**: Access information specifically about Chinese movies and celebrities

## Testing

The skill has been tested with:
- 八佰 (The Eight Hundred) - 2020 war film
- 你好，李焕英 (Hi, Mom) - 2021 comedy film
- Non-existent lemma (404 handling)

All core functions (search, get_lemma, get_movie_info) have been verified working correctly.