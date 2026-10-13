# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Facebook Post Access Skill

Extracts post content and metadata from Facebook posts using Open Graph metadata from the mobile endpoint.

## Features

- **Bypasses login wall**: Uses the mobile Facebook endpoint which exposes Open Graph metadata without requiring authentication
- **Multiple post types supported**:
  - Group posts (`/groups/{group_id}/posts/{post_id}/`)
  - Page posts (`/{page_name}/posts/{post_id}/`)
  - User posts (`/{username}/posts/{post_id}/`)
  - Story links (`/story.php?story_fbid=...`)
  - Photo posts
  - Video posts
  - Watch videos

## Functions

### `get_post`

Fetches a Facebook post and extracts its content and metadata.

**Parameters:**
- `url` (required): The Facebook post URL
- `timeout` (optional): Request timeout in milliseconds (default: 30000)

**Returns:**
```json
{
  "success": true,
  "title": "Post title or author name",
  "description": "Full post content/text",
  "content": "Same as description",
  "image": "Post image URL",
  "post_type": "video.other",
  "canonical_url": "https://www.facebook.com/...",
  "keywords": "Keywords if available",
  "graphql_id": "Encoded post ID",
  "has_video": true,
  "url_info": {
    "post_type": "group_post",
    "group_id": "472793529775085",
    "post_id": "3111868022534276"
  },
  "deeplinks": {
    "android": "fb://native_post/...",
    "ios": "fb://story/?graphqlid=..."
  }
}
```

### `parse_url`

Parses a Facebook URL to extract structured information without fetching the page.

**Parameters:**
- `url` (required): The Facebook URL to parse

**Returns:**
```json
{
  "success": true,
  "url_info": {
    "post_type": "group_post",
    "group_id": "472793529775085",
    "post_id": "3111868022534276",
    "page_name": null,
    "username": null
  },
  "mobile_url": "https://m.facebook.com/groups/..."
}
```

## Supported URL Formats

- `https://www.facebook.com/groups/{group_id}/posts/{post_id}/`
- `https://www.facebook.com/{page_name}/posts/{post_id}/`
- `https://www.facebook.com/{page_name}/posts/{slug}/{post_id}/`
- `https://www.facebook.com/{username}/posts/{post_id}/`
- `https://www.facebook.com/story.php?story_fbid={post_id}&id={user_id}`
- `https://www.facebook.com/{username}/photos/{photo_id}/`
- `https://www.facebook.com/{username}/videos/{video_id}/`
- `https://www.facebook.com/watch/?v={video_id}`

Mobile URLs (`m.facebook.com`, `mbasic.facebook.com`) are also supported and automatically converted.

## Limitations

- **Content truncation**: The Open Graph description may be truncated for very long posts
- **Comments not included**: Only the main post content is extracted, not comments
- **Login-required content**: Some posts from private groups or restricted pages may not be accessible
- **Media URLs**: Image URLs are temporary and may expire

## Example Usage

```python
# Get a group post
result = await execute({
    "function": "get_post",
    "url": "https://www.facebook.com/groups/472793529775085/posts/3111868022534276/"
}, ctx)

# Get a page post  
result = await execute({
    "function": "get_post",
    "url": "https://www.facebook.com/WorldAthletics/posts/992881039534934/"
}, ctx)

# Parse a URL without fetching
result = await execute({
    "function": "parse_url",
    "url": "https://www.facebook.com/groups/12345/posts/67890/"
}, ctx)
```

## Technical Notes

- Uses Playwright with a mobile user agent to access the mobile Facebook endpoint
- Extracts Open Graph metadata (`og:title`, `og:description`, `og:image`, etc.)
- Also extracts Twitter Card metadata and Facebook deep links
- The mobile endpoint (`m.facebook.com`) provides metadata that the desktop site often requires login to access
