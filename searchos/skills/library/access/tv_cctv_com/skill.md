# CCTV Video Page Access Skill

This skill fetches video and program metadata from **tv.cctv.com** (China Central Television's official video platform).

## Supported Page Types

### 1. Video Pages (VIDE*)
Individual video/episode pages with IDs starting with `VIDE`.
- Example: `https://tv.cctv.com/2024/04/08/VIDECKyK80JsMgJTjBcFlXLJ240408.shtml`
- Returns: Video metadata, GUID, album information, and list of all videos in the same album

### 2. Album/Collection Pages (VIDA*)
Album or collection pages containing multiple videos with IDs starting with `VIDA`.
- Example: `https://tv.cctv.com/2023/03/04/VIDAekKSwpiH0NJARZoCDsDH230304.shtml`
- Returns: Album metadata and complete list of videos in the collection

## Functions

### scrape_page
Auto-detect page type and scrape all available metadata.

**Parameters:**
- `url` (required): The tv.cctv.com page URL

**Example:**
```python
result = await execute({
    "function": "scrape_page",
    "url": "https://tv.cctv.com/2024/04/08/VIDECKyK80JsMgJTjBcFlXLJ240408.shtml"
})
```

**Returns:**
- For video pages: video metadata, GUID, album info, and list of related videos
- For album pages: album metadata and all videos in the collection

### get_video_info
Get detailed video information by GUID.

**Parameters:**
- `guid` (required): 32-character hexadecimal GUID

**Example:**
```python
result = await execute({
    "function": "get_video_info",
    "guid": "0d90555d55bc4e809f05a0bde347c29a"
})
```

**Returns:**
- Video title, description, duration, channel, publish time, category, keywords, etc.

### get_album_info
Get album information that contains a specific video.

**Parameters:**
- `video_id` (required): Video ID (starts with VIDE)

**Example:**
```python
result = await execute({
    "function": "get_album_info",
    "video_id": "VIDECKyK80JsMgJTjBcFlXLJ240408"
})
```

**Returns:**
- Album ID, title, URL, description, and other metadata

### get_album_videos
Get all videos in an album/collection.

**Parameters:**
- `album_id` (required): Album ID (starts with VIDA)
- `page` (optional): Page number, default 1
- `page_size` (optional): Videos per page, default 100

**Example:**
```python
result = await execute({
    "function": "get_album_videos",
    "album_id": "VIDA7iCcwXiFGORbpjTBTEdc240407"
})
```

**Returns:**
- Total count, page info, and list of videos with metadata (ID, GUID, title, duration, etc.)

## Data Fields

### Video Metadata
- `video_id`: Video identifier (VIDE...)
- `guid`: 32-char hex identifier used for video playback APIs
- `title`: Video title
- `brief`: Video description/summary
- `url`: Page URL
- `image`: Thumbnail image URL
- `duration`: Video length (HH:MM:SS or MM:SS)
- `channel`: TV channel name (e.g., CCTV-1高清)
- `publish_time`: Publication date and time
- `category`: Primary category (fc)
- `sub_category`: Secondary category (sc)
- `keywords`: Video keywords

### Album Metadata
- `album_id`: Album identifier (VIDA...)
- `album_title`: Album/collection title
- `album_url`: Album page URL
- `album_image`: Album cover image
- `album_brief`: Album description
- `vms_id`: System ID
- `order`: Video's position in album

## Use Cases

1. **Extract episode lists**: Get all episodes from a program series
2. **Video metadata extraction**: Retrieve comprehensive information about specific videos
3. **Program discovery**: Find related videos within the same album/collection
4. **Content aggregation**: Build catalogs of CCTV programs and episodes

## Notes

- The skill uses public API endpoints from api.cntv.cn
- No authentication required
- Responses are in JSON format
- Album pages with VIDX IDs are treated as video variants
- Some older content may have limited metadata availability