# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Linktree Profile Access Skill

Fetches comprehensive profile data from Linktree (linktr.ee) pages.

## Features

- **Profile Information**: Username, page title, description, avatar, verification status
- **Social Links**: Connected social media platforms (Instagram, TikTok, YouTube, Spotify, etc.)
- **All Links**: Complete list of links on the profile with titles, URLs, types, and thumbnails
- **Theme Data**: Profile customization (background, button style, typeface)
- **Group Links**: Supports nested/grouped links with children

## Usage

### Get Profile Data

```
function: get_profile
username: itsmetinx
```

The username parameter accepts:
- Plain username: `itsmetinx`
- With @ prefix: `@bretmanrock`
- Full URL: `https://linktr.ee/paigedesorbo_demo`

## Response Structure

```json
{
  "success": true,
  "error": null,
  "data": {
    "username": "itsmetinx",
    "page_title": "Tinx",
    "description": "...",
    "avatar": "https://...",
    "is_verified": true,
    "tier": "paid2",
    "profile_url": "https://linktr.ee/itsmetinx",
    "social_links": [
      {
        "platform": "INSTAGRAM",
        "url": "https://instagram.com/tinx",
        "position": 1
      }
    ],
    "social_links_count": 5,
    "links": [
      {
        "id": 12345,
        "title": "My New Book",
        "url": "https://...",
        "type": "CLASSIC",
        "position": 1,
        "thumbnail": "https://...",
        "is_locked": false,
        "children": []
      }
    ],
    "links_count": 31,
    "theme": {
      "background": "#ffffff",
      "button_style": "rounded",
      "typeface": "sans-serif"
    },
    "badges": ["VERIFIED_AND_NOTABLE_TICK"]
  }
}
```

## Link Types

Common link types found in profiles:
- `CLASSIC` - Standard link
- `GROUP` - Group/container with children links
- `AMAZON_BOOK` - Amazon book link
- `AMAZON_SHOP` - Amazon storefront
- `YOUTUBE_CHANNEL` - YouTube channel
- `TIKTOK_PROFILE` - TikTok profile
- `SPOTIFY_SHOW` - Spotify podcast/show
- `SHOP_PREVIEW` - Shop/product preview

## Error Handling

- Returns `success: false` for non-existent or private profiles
- Handles password-protected profiles with appropriate error message
- Reports timeout and network errors clearly

## Notes

- Uses Playwright browser automation to render JavaScript-heavy pages
- Extracts data from Next.js `__NEXT_DATA__` JSON payload for reliability
- Works with both free and paid Linktree tiers
- Respects rate limits with reasonable timeouts
