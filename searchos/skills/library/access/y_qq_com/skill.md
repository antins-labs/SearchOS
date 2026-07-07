# QQ Music Access Skill

This skill fetches music data from QQ Music (y.qq.com), one of China's largest music streaming platforms.

## Features

- **Search Songs**: Search for songs by name, artist, or lyrics
- **Get Song Details**: Retrieve comprehensive information about a specific song
- **Get Lyrics**: Fetch synchronized lyrics (LRC format) for songs

## Usage

### Search for Songs

```python
result = await execute({
    "function": "search",
    "query": "告白气球",  # Song name or keyword
    "page": 1,
    "page_size": 10
})
```

Returns a list of matching songs with:
- `song_mid`: Unique song identifier
- `song_id`: Numeric song ID
- `name`: Song name
- `singers`: List of artist names
- `album_name`: Album title
- `album_mid`: Album identifier
- `duration`: Song duration in seconds

### Get Song Details

```python
result = await execute({
    "function": "get_detail",
    "song_mid": "003OUlho2HcRHC"  # Song's mid identifier
})
```

Returns detailed song information including:
- Basic info (name, title, singers)
- Album information with release date
- File sizes for different quality levels (128k, 320k, FLAC)
- BPM, genre, language
- Media identifiers

### Get Lyrics

```python
result = await execute({
    "function": "get_lyrics",
    "song_mid": "003OUlho2HcRHC"
})
```

Returns:
- `lyric`: Full LRC-format lyrics with timestamps
- `title`: Song title extracted from lyrics
- `artist`: Artist name from lyrics metadata
- `album`: Album name from lyrics metadata

## Notes

### About Song IDs

- QQ Music uses `song_mid` (a string like "003OUlho2HcRHC") as the primary identifier
- Use search to find the `song_mid` for a song, then use it for details/lyrics

### API Limitations

- Some songs may not be available due to licensing restrictions
- Lyrics availability varies by song and region
- First search, then get details is the recommended workflow

### Example Workflow

```python
# 1. Search for a song
search_result = await execute({
    "function": "search",
    "query": "晴天 周杰伦"
})

# 2. Get the first result's song_mid
if search_result['songs']:
    song_mid = search_result['songs'][0]['song_mid']
    
    # 3. Get full details
    details = await execute({
        "function": "get_detail",
        "song_mid": song_mid
    })
    
    # 4. Get lyrics
    lyrics = await execute({
        "function": "get_lyrics",
        "song_mid": song_mid
    })
```

## Technical Details

The skill uses QQ Music's public APIs:
- Search API: `shc.y.qq.com/soso/fcgi-bin/search_for_qq_cp`
- Detail API: `c6.y.qq.com/v8/fcg-bin/fcg_play_single_song.fcg`
- Lyrics API: `c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg`

All requests include appropriate headers to mimic browser behavior.