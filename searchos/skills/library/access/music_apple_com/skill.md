# Apple Music API Access Skill

This skill provides programmatic access to Apple Music catalog data, including albums, artists, songs, search functionality, and charts.

## Overview

Apple Music does not provide a publicly documented API for third-party access. However, the web player at `music.apple.com` uses an internal API (`amp-api.music.apple.com`) that can be leveraged to retrieve catalog data. This skill implements that API by:

1. Extracting a developer token (JWT) from the Apple Music web player page
2. Using the token to authenticate requests to the amp-api
3. Parsing and returning structured data about albums, artists, songs, etc.

## Available Functions

### `get_album`

Retrieve detailed information about an album, including its track list.

**Parameters:**
- `album_id` (required): Apple Music album ID (numeric string)
- `storefront` (optional): Region code, default "us"
- `include_tracks` (optional): Include track list, default true

**Example:**
```python
result = await execute({
    "function": "get_album",
    "album_id": "1721453996"
})
```

**Returns:**
- Album name, artist, release date, track count
- Genre, copyright, record label, UPC
- Artwork URLs and colors
- Full track list (if `include_tracks=true`)
- Artist relationships

### `get_artist`

Retrieve information about an artist.

**Parameters:**
- `artist_id` (required): Apple Music artist ID
- `storefront` (optional): Region code, default "us"
- `include_albums` (optional): Include album list, default true

**Example:**
```python
result = await execute({
    "function": "get_artist",
    "artist_id": "300117743"
})
```

### `get_song`

Retrieve information about a specific song.

**Parameters:**
- `song_id` (required): Apple Music song ID
- `storefront` (optional): Region code, default "us"

**Example:**
```python
result = await execute({
    "function": "get_song",
    "song_id": "1721454007"
})
```

### `search`

Search the Apple Music catalog.

**Parameters:**
- `query` (required): Search query (supports both English and other languages)
- `types` (optional): Comma-separated types - "albums,artists,songs"
- `limit` (optional): Max results per type, default 10
- `storefront` (optional): Region code, default "us"

**Example:**
```python
result = await execute({
    "function": "search",
    "query": "周杰伦",
    "types": "albums,artists,songs",
    "limit": 10
})
```

### `get_artist_albums`

Get a list of albums by a specific artist.

**Parameters:**
- `artist_id` (required): Apple Music artist ID
- `limit` (optional): Max number of albums, default 20
- `storefront` (optional): Region code, default "us"

**Example:**
```python
result = await execute({
    "function": "get_artist_albums",
    "artist_id": "300117743",
    "limit": 20
})
```

### `get_charts`

Get current Apple Music charts.

**Parameters:**
- `types` (optional): Chart types - "albums,songs", default "albums,songs"
- `limit` (optional): Max results per chart, default 20
- `storefront` (optional): Region code, default "us"

**Example:**
```python
result = await execute({
    "function": "get_charts",
    "storefront": "us",
    "limit": 20
})
```

## Data Structures

### Album
```json
{
  "id": "1721453996",
  "type": "album",
  "name": "Still Fantasy",
  "artist_name": "Jay Chou",
  "release_date": "2006-09-05",
  "track_count": 10,
  "genre_names": ["Mandopop", "Music", "Pop"],
  "copyright": "℗ 2006 JVR Music International Ltd.",
  "record_label": "Universal Music Taiwan (JVR)",
  "upc": "00602458949179",
  "url": "https://music.apple.com/us/album/...",
  "artwork": {
    "url": "https://is1-ssl.mzstatic.com/...",
    "width": 3000,
    "height": 3000
  },
  "tracks": [...]
}
```

### Artist
```json
{
  "id": "300117743",
  "type": "artist",
  "name": "Jay Chou",
  "genre_names": ["Mandopop", "Pop"],
  "url": "https://music.apple.com/us/artist/...",
  "artwork": {...},
  "albums": [...]
}
```

### Song
```json
{
  "id": "1721454007",
  "type": "song",
  "name": "Chapter Seven",
  "artist_name": "Jay Chou",
  "album_name": "Still Fantasy",
  "duration_ms": 228000,
  "track_number": 1,
  "disc_number": 1,
  "genre_names": ["Mandopop"],
  "url": "https://music.apple.com/us/song/..."
}
```

## Finding IDs

Apple Music IDs can be found in the URLs of Apple Music web pages:

- Album: `https://music.apple.com/us/album/album-name/1721453996` → ID is `1721453996`
- Artist: `https://music.apple.com/us/artist/jay-chou/300117743` → ID is `300117743`
- Song: `https://music.apple.com/us/song/chapter-seven/1721454007` → ID is `1721454007`

Or use the `search` function to find IDs by name.

## Storefronts

Common storefront codes:
- `us` - United States
- `cn` - China
- `jp` - Japan
- `gb` - United Kingdom
- `au` - Australia
- `de` - Germany
- `fr` - France

## Notes

- The developer token is extracted from the Apple Music web player and cached for 1 hour
- Token extraction requires loading a web page with Playwright (headless Chromium)
- The API returns data in JSON format similar to the official Apple Music API
- Artwork URLs contain placeholders `{w}x{h}` that should be replaced with desired dimensions

## Limitations

- This skill can only access catalog data (public music information)
- User library data (playlists, favorites, etc.) requires authentication
- Some content may vary by storefront/region due to licensing
- Rate limiting may apply; the skill caches tokens to minimize page loads