# Apple App Store Access Skill

Fetch comprehensive metadata for iOS/iPadOS apps from Apple's iTunes Search API.

## Features

- **App Lookup by ID**: Retrieve detailed app information using App Store ID(s)
- **Bundle ID Lookup**: Find apps using their bundle identifier (e.g., `com.burbn.instagram`)
- **App Search**: Search the App Store by name or keywords

## Supported Functions

### lookup_app

Look up one or more apps by their App Store IDs.

**Parameters:**
- `app_id` (required): Single app ID like `"835599320"` or comma-separated IDs like `"835599320,389801252"`
- `country` (optional): Two-letter country code, defaults to `"us"`

**Returns:** App metadata including name, developer, ratings, pricing, version info, screenshots, and more.

### lookup_by_bundle_id

Look up an app using its bundle identifier.

**Parameters:**
- `bundle_id` (required): Bundle ID like `"com.burbn.instagram"`
- `country` (optional): Two-letter country code, defaults to `"us"`

**Returns:** Single app's complete metadata.

### search_apps

Search for apps in the App Store.

**Parameters:**
- `query` (required): Search query string
- `country` (optional): Two-letter country code, defaults to `"us"`
- `limit` (optional): Maximum results (1-200), defaults to 10
- `offset` (optional): Pagination offset, defaults to 0

**Returns:** List of matching apps with metadata.

## Data Fields

Each app result includes:

| Field | Description |
|-------|-------------|
| `id` | App Store ID |
| `name` | App name |
| `bundle_id` | Bundle identifier |
| `developer` | Developer name |
| `price` | Numeric price (0 = free) |
| `formatted_price` | Display price string |
| `average_rating` | User rating (out of 5) |
| `rating_count` | Total number of ratings |
| `category` | Primary category |
| `genres` | List of all genres |
| `version` | Current version number |
| `size_bytes` | App size in bytes |
| `size_formatted` | Human-readable size |
| `release_date` | Original release date |
| `current_version_release_date` | Latest update date |
| `description` | App description |
| `content_rating` | Age rating (e.g., "12+") |
| `app_store_url` | Link to App Store page |
| `artwork_url_*` | App icon URLs |
| `screenshot_urls` | Screenshot image URLs |

## Example Usage

```python
# Look up TikTok by ID
result = await execute({
    "function": "lookup_app",
    "app_id": "835599320"
})

# Look up multiple apps
result = await execute({
    "function": "lookup_app",
    "app_id": "835599320,389801252,284882215",
    "country": "gb"
})

# Find app by bundle ID
result = await execute({
    "function": "lookup_by_bundle_id",
    "bundle_id": "com.burbn.instagram"
})

# Search for photo editing apps
result = await execute({
    "function": "search_apps",
    "query": "photo editor",
    "limit": 20
})
```

## Notes

- The iTunes Search API is a public Apple API with no authentication required
- Data reflects the App Store state at query time
- Some apps may not be available in all countries
- Ratings and review counts are updated in real-time