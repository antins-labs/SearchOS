# RateYourMusic Access Skill

This skill provides access to RateYourMusic (RYM), one of the most comprehensive community-driven music databases featuring ratings, reviews, credits, and tracklists for albums, singles, EPs, and more.

## Features

- **Release Information**: Fetch detailed release data including:
  - Artist and title
  - Release type (album, single, EP, mixtape, compilation, etc.)
  - Release year
  - Community ratings (average and vote count)
  - Genres and descriptors
  - Track listings
  - Credits and personnel
  - JSON-LD structured data

- **Multiple Access Methods**:
  - curl_cffi with browser impersonation (Chrome, Safari, Edge)
  - Playwright browser automation with JavaScript challenge solving
  - aiohttp as fallback

## Limitations

⚠️ **Important**: RateYourMusic uses heavy Cloudflare protection that actively blocks automated access. This skill attempts multiple strategies to bypass the protection but may frequently encounter blocking.

The skill is designed to:
1. Attempt access with multiple methods
2. Detect when blocked (Cloudflare challenge pages)
3. Return detailed attempt information
4. Provide helpful error messages and alternatives

## Functions

### get_release_info

Fetch information about a specific release.

**Parameters:**
- `url`: Direct URL to the release page
- `artist`: Artist name (used with `title`)
- `title`: Release title (used with `artist`)
- `release_type`: Type of release (album, single, ep, etc.)
- `slug`: Direct slug path

**Example - Using URL:**
```json
{
  "function": "get_release_info",
  "url": "https://rateyourmusic.com/release/album/radiohead/ok-computer/"
}
```

**Example - Using artist/title:**
```json
{
  "function": "get_release_info",
  "artist": "Radiohead",
  "title": "OK Computer",
  "release_type": "album"
}
```

### search

Search RateYourMusic for releases.

**Note**: Currently blocked by Cloudflare protection.

**Parameters:**
- `query`: Search query
- `release_type`: Filter by type (optional)
- `limit`: Maximum results (default: 10)

**Example:**
```json
{
  "function": "search",
  "query": "Pink Floyd Dark Side of the Moon",
  "limit": 5
}
```

## Return Structure

### Success Response
```json
{
  "success": true,
  "url": "https://rateyourmusic.com/release/album/radiohead/ok-computer/",
  "data": {
    "title": "OK Computer",
    "artist": "Radiohead",
    "type": "album",
    "year": "1997",
    "rating": 4.21,
    "votes": 145000,
    "genres": ["Art Rock", "Alternative Rock"],
    "tracks": ["Airbag", "Paranoid Android", "..."],
    "json_ld": {...}
  },
  "attempts": [
    {
      "method": "curl_cffi",
      "status": 200,
      "blocked": false
    }
  ]
}
```

### Error/Blocked Response
```json
{
  "success": false,
  "error": "RateYourMusic is currently blocking automated access...",
  "attempts": [
    {
      "method": "curl_cffi",
      "status": 403,
      "blocked": true
    },
    {
      "method": "playwright",
      "status": 200,
      "blocked": true
    }
  ]
}
```

## Why RateYourMusic?

RateYourMusic is valuable for:
- **Accurate Ratings**: Community-driven ratings from music enthusiasts
- **Comprehensive Credits**: Detailed personnel information (producers, engineers, musicians)
- **Track Listings**: Full track information with durations
- **Release Variants**: Multiple pressings, editions, and formats
- **Genre Classification**: Detailed subgenre tagging

## Alternatives When Blocked

When RateYourMusic is blocking access, consider these alternatives:
- **MusicBrainz API**: Open music database with comprehensive metadata
- **Discogs Marketplace**: Release information and marketplace data
- **Last.fm API**: Music metadata and scrobbling data
- **Spotify API**: Official release information (requires auth)

## Technical Notes

The skill uses several anti-detection techniques:
- Browser impersonation with curl_cffi
- Headless browser automation with Playwright
- JavaScript challenge detection and waiting
- TLS fingerprint spoofing
- Realistic user agent strings

However, Cloudflare's protection is sophisticated and frequently updated. Access success varies based on:
- IP reputation
- Current Cloudflare protection level
- Time of day and traffic patterns
- Previous access attempts from the same IP

## Dependencies

- `curl_cffi`: For browser impersonation
- `playwright`: For browser automation
- `aiohttp`: For HTTP requests

These are optional - the skill will attempt all available methods.