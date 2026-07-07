# Spotify Track Access Skill

This skill fetches track metadata from Spotify without requiring authentication.

## Capabilities

### get_track
Fetches comprehensive track metadata including:
- **Basic Info**: ID, title, duration, release date
- **Artists**: List of artist names and URIs
- **Playback**: Playability status, explicit flag, has video
- **Media**: Cover images in multiple sizes (64x64, 300x300, 640x640)
- **Audio Preview**: URL to MP3 preview clip (30 seconds)
- **Visual Identity**: Themed colors for UI display
- **oEmbed**: Embed iframe HTML and thumbnail (optional)

### get_track_basic
Lightweight alternative that fetches basic track info from Spotify's oEmbed API:
- Title
- Thumbnail image
- Embed iframe HTML

## Data Sources

The skill uses two public endpoints that don't require authentication:

1. **Embed Page** (`https://open.spotify.com/embed/track/{id}`)
   - Contains `__NEXT_DATA__` JSON with full track metadata
   - Primary source for complete track information

2. **oEmbed API** (`https://open.spotify.com/oembed?url=...`)
   - Standard oEmbed format for embedding
   - Provides title and thumbnail only

## Input Formats

The `track_id` parameter accepts multiple formats:

```
# Full URL
https://open.spotify.com/track/1jwwyhTZw5QRFnCCmCdhT5

# Spotify URI
spotify:track:1jwwyhTZw5QRFnCCmCdhT5

# Plain track ID
1jwwyhTZw5QRFnCCmCdhT5
```

## Example Output

```json
{
  "id": "1jwwyhTZw5QRFnCCmCdhT5",
  "type": "track",
  "title": "亲爱的你啊（电视剧《无尽的尽头》主题曲）",
  "artists": [
    {
      "name": "任素汐",
      "uri": "spotify:artist:16rAFXQVz2WBpTH9uc1LA8",
      "id": "16rAFXQVz2WBpTH9uc1LA8"
    }
  ],
  "duration_ms": 235750,
  "duration_seconds": 235,
  "release_date": "2025-04-24T00:00:00Z",
  "is_playable": true,
  "playability_reason": "PLAYABLE",
  "is_explicit": false,
  "has_video": false,
  "spotify_url": "https://open.spotify.com/track/1jwwyhTZw5QRFnCCmCdhT5",
  "audio_preview_url": "https://p.scdn.co/mp3-preview/...",
  "cover_images": [
    {
      "url": "https://image-cdn-ak.spotifycdn.com/image/...",
      "maxHeight": 300,
      "maxWidth": 300
    }
  ],
  "oembed": {
    "title": "亲爱的你啊（电视剧《无尽的尽头》主题曲）",
    "thumbnail_url": "https://image-cdn-ak.spotifycdn.com/image/...",
    "iframe_html": "<iframe ...>"
  }
}
```

## Error Handling

The skill returns structured errors instead of raising exceptions:

```json
{
  "error": "missing_parameter",
  "error_detail": "track_id is required"
}
```

Common errors:
- `missing_parameter`: Required parameter not provided
- `HTTP 404`: Track not found
- `parse_error`: Could not parse embed page
- `no_data`: No entity data found

## Limitations

- **No album information**: The embed page doesn't include album data
- **No track popularity/numbers**: Play counts, popularity scores not available
- **Basic artist info**: Only artist names and URIs, no detailed artist metadata
- **Preview audio only**: Full track audio requires Spotify authentication

For full track details including album info, consider using the official Spotify Web API with authentication.