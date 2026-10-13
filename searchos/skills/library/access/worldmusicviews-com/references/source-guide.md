# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# World Music Views - RIAA Diamond Albums

## Overview

This skill retrieves the complete list of RIAA Diamond certified albums from World Music Views (worldmusicviews.com). The Diamond certification is one of the most prestigious awards in the music industry, requiring 10 million units sold in the United States.

## Features

- **Complete Album List**: Fetches all 117+ Diamond and Diamante certified albums
- **Detailed Information**: Includes artist name, album title, certification date, record label, and album type
- **Filtering Options**: Filter by artist name, year range, or limit results
- **Latin Albums**: Includes Diamante certified Latin albums (1 million units before Dec 2013, 600,000 after)

## Available Functions

### get_riaa_diamond_albums

Retrieves the list of RIAA Diamond certified albums with optional filtering.

**Parameters:**
- `artist` (optional): Filter by artist name (case-insensitive partial match)
- `min_year` (optional): Minimum certification year
- `max_year` (optional): Maximum certification year
- `limit` (optional): Maximum number of results to return

**Example Usage:**

```json
// Get all Diamond albums
{
  "function": "get_riaa_diamond_albums"
}

// Filter by artist
{
  "function": "get_riaa_diamond_albums",
  "artist": "Eminem"
}

// Filter by year range
{
  "function": "get_riaa_diamond_albums",
  "min_year": 2020,
  "max_year": 2023
}

// Get recent certifications
{
  "function": "get_riaa_diamond_albums",
  "min_year": 2022,
  "limit": 10
}
```

**Response Format:**

```json
{
  "success": true,
  "url": "https://worldmusicviews.com/riaadiamond/",
  "total_albums": 117,
  "filtered_count": 10,
  "albums": [
    {
      "artist": "Artist Name",
      "album": "Album Title",
      "date": "Month Day, Year",
      "year": 2023,
      "label": "Record Label",
      "type": "Album",
      "raw": "Original line from page"
    }
  ],
  "metadata": {
    "source": "World Music Views",
    "title": "All The Albums That Have Been Certified Diamond® By The RIAA",
    "last_updated": "June 21, 2023",
    "note": "Diamond certification requires 10 million units sold in the US..."
  }
}
```

## Data Source

- **Website**: World Music Views (worldmusicviews.com)
- **Page**: https://worldmusicviews.com/riaadiamond/
- **Last Updated**: June 21, 2023
- **Total Albums**: 117 Diamond and Diamante certified albums

## Notable Artists

- **Garth Brooks**: 9 Diamond albums (most of any artist)
- **The Beatles**: 6 Diamond albums
- **Led Zeppelin**: 5 Diamond albums
- **Eminem**: 3 Diamond albums
- **Shania Twain**: 3 Diamond albums
- **The Eagles**: 3 Diamond albums
- **Whitney Houston**: 3 Diamond albums

## Notes

- The page includes both Diamond (10 million units) and Diamante (Latin albums) certifications
- Diamante certification requirements: 1 million units before December 2013, 600,000 units after
- The Eagles' Greatest Hits (1971-1975) is the most commercially successful album with 38+ million units
- Data is scraped from the webpage and may not reflect real-time RIAA updates

## Technical Details

- Uses Playwright for browser automation to handle dynamic content
- Parses structured album data from page text content
- Handles various date formats and album entry patterns
- Includes error handling for navigation timeouts
