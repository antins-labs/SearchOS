# The Game Awards Rewind Skill

## Overview

This skill extracts award winners, nominees, and show highlights from The Game Awards rewind pages (`thegameawards.com/rewind`). It provides structured access to annual award data from 2014 onwards.

## Available Functions

### `list_years`
List all available years for The Game Awards rewind data.

**Parameters:** None

**Returns:**
```json
{
  "success": true,
  "data": {
    "years": [2014, 2015, 2016, ..., 2024],
    "note": "The Game Awards started in 2014. Not all years may have data available."
  }
}
```

### `get_rewind`
Fetch complete rewind data for a specific year, including winners, highlights, hero information, and recap video.

**Parameters:**
- `year` (integer, required): The year to fetch (e.g., 2019, 2014)

**Returns:**
```json
{
  "success": true,
  "data": {
    "year": "2019",
    "title": "2019",
    "slug": "year-2019",
    "preview": {
      "caption": "Viewership: 49 Million",
      "subcaption": "Aired Dec 12"
    },
    "hero": {
      "headline": "A NEW XBOX, GREEN DAY, THE MUPPETS, AND MORE!",
      "subheadline": "Seen by 50 million people globally...",
      "backgroundImageUrl": "https://..."
    },
    "recap": {
      "videoOverlayImageUrl": "https://...",
      "youtubeVideoId": "jxAihuiYxuU"
    },
    "highlights": [...],
    "winners": [...]
  }
}
```

### `get_winners`
Fetch only the winners for a specific year.

**Parameters:**
- `year` (integer, required): The year to fetch (e.g., 2019, 2014)

**Returns:**
```json
{
  "success": true,
  "data": {
    "year": "2019",
    "winners": [
      {
        "imageUrl": "https://cdn.thegameawards.com/...",
        "awardCategory": "Game of the Year",
        "title": "Sekiro: Shadows Die Twice",
        "caption": "Activision / FromSoftware"
      },
      ...
    ]
  }
}
```

### `get_highlights`
Fetch only the show highlights for a specific year.

**Parameters:**
- `year` (integer, required): The year to fetch (e.g., 2019, 2014)

**Returns:**
```json
{
  "success": true,
  "data": {
    "year": "2019",
    "highlights": [
      {
        "imageUrl": "https://cdn.thegameawards.com/...",
        "categoryName": "Show Highlight",
        "title": "THE XBOX SERIES X REVEAL",
        "caption": "Microsoft shocks the world...",
        "isFeaturedHighlight": true,
        "highlightURL": "https://youtu.be/..."
      },
      ...
    ]
  }
}
```

## Data Structure

### Winner Object
Each winner contains:
- `imageUrl`: URL to the winner's image
- `awardCategory`: The category name (e.g., "Game of the Year", "Best Art Direction")
- `title`: The winner's name (game, person, or team)
- `caption`: Publisher, developer, or additional context

### Highlight Object
Each highlight contains:
- `imageUrl`: URL to the highlight image
- `categoryName`: Type of highlight (e.g., "Show Highlight", "Trending Moment")
- `title`: The highlight title
- `caption`: Description of the moment
- `isFeaturedHighlight`: Boolean indicating if it's a featured highlight
- `highlightURL`: YouTube URL to the specific moment

## Examples

### Get all 2019 winners
```python
result = await execute({
    "function": "get_winners",
    "year": 2019
})
```

### Get complete rewind for 2014
```python
result = await execute({
    "function": "get_rewind",
    "year": 2014
})
```

## Technical Details

This skill uses Next.js RSC (React Server Components) endpoints to extract structured JSON data directly from The Game Awards website. The data is embedded in the page response and extracted without requiring browser automation.

## Error Handling

The skill returns structured error responses:
```json
{
  "success": false,
  "error": "Error message here"
}
```

Common errors:
- Missing `year` parameter for functions that require it
- Invalid year (year not available)
- Network errors
- Parsing failures