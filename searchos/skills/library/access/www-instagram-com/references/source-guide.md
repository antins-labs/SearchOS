# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Instagram Media Page Access Skill

This skill extracts structured metadata from Instagram media pages (posts, reels, and TV videos) without requiring authentication.

## Features

- **No Login Required**: Works by parsing server-rendered Open Graph and Twitter Card meta tags
- **Rich Metadata**: Extracts caption, likes, comments, author info, timestamps, and media URLs
- **Multiple Media Types**: Supports posts (`/p/`), reels (`/reel/`), and IGTV (`/tv/`)
- **Error Handling**: Gracefully handles unavailable, deleted, or private posts

## How It Works

Instagram embeds rich metadata in HTML meta tags for SEO and social sharing purposes. These tags are rendered server-side and available even when:
- The user is not logged in
- A login wall is displayed
- JavaScript is disabled

This skill uses Playwright to fetch the page and extract the following meta tags:
- `description` - Contains likes, comments, username, date, and caption
- `twitter:title` - Contains author name and username
- `og:image` / `twitter:image` - Post thumbnail
- `al:ios:url` - Contains the internal media ID
- `og:url` - Canonical URL

## Usage

### Get Media Info

Fetch metadata from an Instagram media URL:

```json
{
  "function": "get_media_info",
  "url": "https://www.instagram.com/reel/DZaHhB1Jx1I/"
}
```

**Response:**

```json
{
  "success": true,
  "url": "https://www.instagram.com/reel/DZaHhB1Jx1I/",
  "media_id": "3916475881985875272",
  "shortcode": "DZaHhB1Jx1I",
  "username": "terraandtime",
  "full_name": "Terra and Time",
  "caption": ".🇹🇷 Turkey shares borders with 8 countries...",
  "likes": 256,
  "comments": 1,
  "timestamp": "June 10, 2026",
  "media_type": "video",
  "is_video": true,
  "thumbnail_url": "https://scontent-iad3-2.cdninstagram.com/...",
  "canonical_url": "https://www.instagram.com/terraandtime/reel/DZaHhB1Jx1I/"
}
```

### Supported URL Formats

- Standard posts: `https://www.instagram.com/p/SHORTCODE/`
- Reels: `https://www.instagram.com/reel/SHORTCODE/`
- IGTV: `https://www.instagram.com/tv/SHORTCODE/`
- User-specific URLs: `https://www.instagram.com/USERNAME/reel/SHORTCODE/`

## Limitations

- **Private accounts**: Cannot access posts from private accounts (returns error)
- **Stories**: Not supported (stories expire and require authentication)
- **Carousels**: Returns metadata for the post but does not enumerate all media items
- **Video URLs**: Does not extract direct video file URLs (only thumbnail)
- **Real-time data**: Data is from the initial page load; dynamic updates after page load are not captured

## Error Handling

The skill returns descriptive errors for common failure cases:

- **Invalid URL**: URL is not a valid Instagram media URL
- **Post unavailable**: Post has been deleted, link is incorrect, or account is private
- **Timeout**: Page took too long to load
- **Network error**: Failed to reach Instagram servers

## Technical Details

- Uses Playwright with Chromium for reliable page rendering
- User agent spoofing to avoid basic bot detection
- 30-second timeout for page loads
- 2-second wait after page load to ensure meta tags are rendered
