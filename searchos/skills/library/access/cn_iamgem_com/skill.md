# G.E.M.邓紫棋 Official Website Access Skill

This skill provides programmatic access to G.E.M.邓紫棋 (Gloria Tang Tsz-kei) official website at cn.iamgem.com, extracting tours, music albums, tracks, and video content.

## Overview

The site is a WordPress-powered official website for the Hong Kong singer-songwriter G.E.M. It contains:
- **Tours**: Upcoming and past tour dates with venue information
- **Music**: Albums and individual tracks organized by categories
- **Videos**: Music videos and official MV releases

## Site Structure

### Data Access Methods

1. **WordPress REST API**: Music and video content is accessible via standard WordPress REST API endpoints
   - Base API: `https://cn.iamgem.com/wp-json/wp/v2/`
   - Categories represent albums
   - Posts represent individual songs/tracks/MVs

2. **HTML Parsing**: Tour dates are dynamically rendered and require HTML parsing
   - Tours page: `https://cn.iamgem.com/tours/`

## Available Functions

### 1. get_tours

Get all tour dates with venue and location information.

**Parameters**: None

**Returns**:
```json
{
  "success": true,
  "count": 15,
  "tours": [
    {
      "dates": "2025/12/26-28、31，2026/1/3-4、9、10-13",
      "location": "广州",
      "venue": "广东省奥林匹克体育中心体育场"
    }
  ]
}
```

### 2. get_albums

Get all music albums/categories.

**Parameters**: None

**Returns**:
```json
{
  "success": true,
  "count": 13,
  "albums": [
    {
      "id": 37,
      "name": "《启示录》",
      "slug": "%e5%90%af%e7%a4%ba%e5%bd%95",
      "description": "",
      "track_count": 14,
      "link": "https://cn.iamgem.com/category/qishilu/"
    }
  ]
}
```

### 3. get_album_tracks

Get all tracks in a specific album.

**Parameters**:
- `album_id` (required): The album/category ID

**Returns**:
```json
{
  "success": true,
  "album": {
    "id": 37,
    "name": "《启示录》",
    "description": "",
    "link": "https://cn.iamgem.com/category/qishilu/"
  },
  "track_count": 14,
  "tracks": [
    {
      "id": 39588,
      "title": "El Joven y El Mar",
      "link": "https://cn.iamgem.com/revelacion/el-joven-y-el-mar/",
      "date": "2024-03-13T17:27:26",
      "featured_image": {
        "url": "https://cn.iamgem.com/wp-content/uploads/...",
        "alt": ""
      }
    }
  ]
}
```

### 4. get_posts

Get posts/songs with optional filtering.

**Parameters**:
- `category_id` (optional): Filter by category/album ID
- `per_page` (optional, default 100): Number of results per page (max 100)
- `page` (optional, default 1): Page number

**Returns**: List of posts with metadata

### 5. get_post

Get a single post/song by ID with full content.

**Parameters**:
- `post_id` (required): The post ID

**Returns**: Complete post data including content, featured image, and embedded videos

### 6. get_categories

Get all categories (same as albums, but without track counts).

**Parameters**: None

### 7. search

Search posts/songs by keyword.

**Parameters**:
- `query` (required): Search keyword
- `per_page` (optional, default 20): Number of results

**Returns**: Matching posts with titles and excerpts

### 8. get_videos

Get video content from the videos page.

**Parameters**: None

**Returns**:
```json
{
  "success": true,
  "count": 14,
  "videos": [
    {
      "date": "May 27 2025",
      "title": "G.E.M.邓紫棋【启示录】Official MV连续剧 (全旅程版)",
      "chapter": null
    }
  ],
  "embedded_videos": ["https://player.bilibili.com/..."]
}
```

## Example Usage

```python
# Get all tour dates
result = await execute({"function": "get_tours"})

# Get all albums
result = await execute({"function": "get_albums"})

# Get tracks from "启示录" album (ID: 37)
result = await execute({
    "function": "get_album_tracks",
    "album_id": 37
})

# Search for songs with "Grace" in the title
result = await execute({
    "function": "search",
    "query": "Grace"
})

# Get a specific song
result = await execute({
    "function": "get_post",
    "post_id": 39609
})
```

## Data Notes

### Tours
- Tour dates are in Chinese format (e.g., "2025/12/26-28、31")
- Locations are typically Chinese city names
- Venues are full venue names in Chinese

### Music
- Categories represent albums (e.g., "《启示录》", "《T.I.M.E.》")
- Albums have both Chinese and English titles
- Some albums contain songs in both Chinese and Spanish
- Featured images are typically album artwork or promotional images

### Videos
- Videos page includes embedded Bilibili players
- Videos are organized by album/chapter
- Some videos are part of a series (indicated by chapter numbers)

## Available Albums

Known album categories include:
1. 《Amazing Grace》
2. 《Revelación》 - Spanish album
3. 《T.I.M.E.》
4. 《万国觉醒》 - 万国觉醒
5. 《两个你》
6. 《倒流时间》
7. 《启示录》 - Revelation
8. 《孤独》
9. 《平凡天使》
10. 《平行世界》 - Parallel World
11. 《摩天动物园》 - City Zoo
12. 《无双的王者》
13. 《超能力》 - Superpower

## Error Handling

All functions return a consistent format:
- On success: `{"success": true, ...data}`
- On error: `{"success": false, "error": "error message"}`

## Rate Limiting

The skill implements:
- Request timeout: 30 seconds
- Recommended rate: 2 requests per second
- Burst limit: 5 requests

## Dependencies

- `aiohttp`: For async HTTP requests
- `beautifulsoup4`: For HTML parsing
- Python 3.7+ with asyncio support