# TotalMusicAwards.com Grammy Awards Database

## Overview

This skill provides access to TotalMusicAwards.com's comprehensive Grammy Awards database, which contains winners and nominees organized by category and year. The database covers major Grammy categories from the awards' inception to the present day.

## Available Functions

### list_categories

Lists all available Grammy Award categories in the database.

**Example:**
```json
{
  "function": "list_categories"
}
```

**Response includes:**
- Category names (e.g., "Album of the Year", "Best New Artist")
- URL slugs for each category
- Full URLs to category pages

### get_category

Fetches winners and nominees for a specific Grammy category with optional year filtering.

**Parameters:**
- `category` (required): Category name or slug (see list below)
- `year` (optional): Filter to a specific year
- `min_year` (optional): Filter to years >= this value
- `max_year` (optional): Filter to years <= this value
- `url` (optional): Direct URL override

**Example - Get all years:**
```json
{
  "function": "get_category",
  "category": "best-melodic-rap-performance"
}
```

**Example - Filter by year range:**
```json
{
  "function": "get_category",
  "category": "album-of-the-year",
  "min_year": 2020,
  "max_year": 2025
}
```

**Example - Get specific year:**
```json
{
  "function": "get_category",
  "category": "best-new-artist",
  "year": 2024
}
```

## Available Categories

Major categories include:
- **General Field**: Album of the Year, Record of the Year, Song of the Year, Best New Artist
- **Pop**: Best Pop Solo Performance, Best Pop Duo/Group Performance, Best Pop Vocal Album
- **Rock/Alternative**: Best Rock Album, Best Alternative Music Album
- **Rap**: Best Rap Album, Best Rap Song, Best Rap Performance, Best Melodic Rap Performance
- **R&B**: Best R&B Performance, Best Progressive R&B Album, Best Contemporary R&B Album
- **Country**: Best Country Album, Best Country Solo Performance, Best Country Duo/Group Performance
- **Other**: Best Comedy Album, Producer of the Year, Songwriter of the Year, Best Album Cover

Use `list_categories` for the complete list of 35+ categories.

## Response Structure

Each `get_category` response includes:

```json
{
  "success": true,
  "category_name": "Best Melodic Rap Performance: Grammy Winners & Nominees By Year",
  "author": "Scott Shetler",
  "notes": ["This award was known as..."],
  "most_nominations": [
    {"artist": "Kanye West", "count": 15},
    {"artist": "Jay-Z", "count": 12}
  ],
  "most_wins": [
    {"artist": "Jay-Z", "count": 7},
    {"artist": "Rihanna", "count": 5}
  ],
  "awards_by_year": {
    "2024": {
      "winner": "All My Life, Lil Durk featuring J. Cole",
      "nominees": [
        "Sittin' on Top of the World, Burna Boy featuring 21 Savage",
        "Attention, Doja Cat",
        ...
      ]
    }
  },
  "total_years": 25,
  "source_url": "https://totalmusicawards.com/..."
}
```

## Data Notes

- **Winners** are listed first for each year (in bold on the website)
- **Nominees** follow the winner for each year
- Some categories include historical notes about name changes (e.g., "Best Melodic Rap Performance" was previously "Best Rap/Sung Collaboration")
- Career statistics (most nominations/wins) are included when available
- Data spans from the category's inception to the most recent Grammy ceremony

## Technical Notes

This skill uses Playwright to retrieve content because the website employs bot protection that blocks simple HTTP requests. The browser instance is reused across requests for efficiency.