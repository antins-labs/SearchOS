# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# TikTok Creator Profile Access Skill

Fetches creator statistics and profile information from TikTok profile pages.

## Features

- **Creator Profile Data**: Retrieves comprehensive profile information including:
  - Username and display name (nickname)
  - Follower count, following count, like count
  - Video count
  - Verification status
  - Bio/description
  - Avatar URL
  - Account creation timestamp
  - Privacy settings

## Functions

### `get_creator_profile`

Fetches profile data for a TikTok creator.

**Parameters:**
- `username` (string, required): TikTok username without the @ symbol

**Example:**
```json
{
  "function": "get_creator_profile",
  "username": "kai_cenat"
}
```

**Returns:**
```json
{
  "success": true,
  "username": "kai_cenat",
  "nickname": "Kai Cenat",
  "bio": "",
  "verified": true,
  "private_account": false,
  "avatar_url": "https://...",
  "profile_url": "https://www.tiktok.com/@kai_cenat",
  "stats": {
    "followers": 22700000,
    "following": 31,
    "likes": 206000000,
    "video_count": 87
  },
  "stats_exact": {
    "followers": 22654267,
    "following": 31,
    "likes": 205969976,
    "video_count": 87
  },
  "stats_formatted": {
    "followers": "22.7M",
    "following": "31",
    "likes": "206.0M",
    "video_count": 87
  },
  "user_id": "6771667630785938437",
  "sec_uid": "MS4wLjABAAAAxdiClc8-RXBZpX7qt8wzXepwEivx7GyuaBzEKO0nqfb9cg4_dQhfMI7pD2ObdLO5",
  "create_time": 1576654129
}
```

## Data Notes

- **stats**: Rounded/approximate values as displayed on TikTok (e.g., 22.7M followers)
- **stats_exact**: Exact integer values from TikTok's internal data
- **stats_formatted**: Human-readable formatted strings with K/M/B suffixes

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "profile_data_not_found",
  "message": "Could not find profile data on page. The profile may not exist..."
}
```

Common errors:
- `missing_username`: No username provided
- `profile_data_not_found`: Profile doesn't exist or page structure changed
- `timeout`: Page load timed out
- `api_error`: TikTok returned an error status

## Technical Details

- Uses browser automation (Playwright) to render the dynamic TikTok page
- Extracts data from the `__UNIVERSAL_DATA_FOR_REHYDRATION__` script tag
- Waits for JavaScript hydration to ensure data is available
- No API authentication required
