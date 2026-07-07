# Douban Movie Access Skill

Fetches movie details and celebrity information from [Douban Movies](https://movie.douban.com), China's largest movie database and review platform.

## Overview

Douban Movies is a comprehensive movie database with Chinese user ratings, reviews, and detailed cast/crew information. This skill provides structured access to:

- Movie metadata (title, year, rating, genres, runtime, etc.)
- Cast and crew information
- Release dates and alternate titles
- Plot summaries

## Functions

### get_movie_detail

Fetches comprehensive movie information including:

- **Basic Info**: Title (Chinese/English), year, poster
- **Rating**: User rating (0-10) and vote count from Douban users
- **People**: Directors and main cast members
- **Details**: Genres, runtime, release dates, country, language
- **External**: IMDb ID when available
- **Summary**: Plot synopsis in Chinese

Example:
```python
result = await execute({
    'function': 'get_movie_detail',
    'subject_id': '1292052'  # The Shawshank Redemption
})
```

Returns:
```json
{
  "subject_id": "1292052",
  "title": "肖申克的救赎 The Shawshank Redemption",
  "year": "(1994)",
  "rating": "9.7",
  "rating_count": "3297574",
  "directors": [
    {"name": "弗兰克·德拉邦特", "url": "https://www.douban.com/personage/..." }
  ],
  "stars": [
    {"name": "蒂姆·罗宾斯", "url": "https://www.douban.com/personage/..." },
    {"name": "摩根·弗里曼", "url": "https://www.douban.com/personage/..." }
  ],
  "genres": ["剧情", "犯罪"],
  "runtime": "142分钟",
  "country": "美国",
  "language": "英语",
  "imdb_id": "tt0111161",
  "summary": "..."
}
```

### get_movie_celebrities

Fetches the complete cast and crew list with roles:

- **Directors**: 导演
- **Writers**: 编剧
- **Actors**: 演员 with character names
- **Producers**: 制片人
- **Other Crew**: 摄影指导, etc.

Example:
```python
result = await execute({
    'function': 'get_movie_celebrities',
    'subject_id': '1292052'
})
```

Returns:
```json
{
  "subject_id": "1292052",
  "total": 45,
  "celebrities": [
    {
      "name": "弗兰克·德拉邦特 Frank Darabont",
      "role": "导演 Director",
      "url": "https://www.douban.com/personage/...",
      "photo": "https://..."
    },
    {
      "name": "蒂姆·罗宾斯 Tim Robbins",
      "role": "演员 Actor (饰 Andy Dufresne)",
      "url": "https://www.douban.com/personage/...",
      "photo": "https://..."
    }
  ]
}
```

## Finding Subject IDs

The `subject_id` can be extracted from Douban movie URLs:

- URL: `https://movie.douban.com/subject/1292052/`
- Subject ID: `1292052`

You can find movie pages by:
1. Searching on Douban website
2. Using Douban's search suggestions
3. Using external movie databases that link to Douban

## Notes

- **Rate Limiting**: Douban has anti-scraping measures. Requests may be slow.
- **Challenge Handling**: The skill uses Playwright to handle JavaScript-based bot detection.
- **Language**: Content is primarily in Chinese, with English names provided where available.
- **402 Errors**: The generic reader fails on this site due to anti-bot challenges. This skill uses browser automation to bypass them.

## Data Quality

Douban is known for:
- High-quality user ratings from millions of Chinese moviegoers
- Comprehensive Chinese/English movie information
- Accurate cast and crew data
- Detailed release information for Chinese market

## Use Cases

- Chinese movie market research
- Cross-referencing movie ratings between platforms
- Building bilingual movie databases
- Analyzing Chinese audience preferences
- Fetching cast and crew information for movies released in China