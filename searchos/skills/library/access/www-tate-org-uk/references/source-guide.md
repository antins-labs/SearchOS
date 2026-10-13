# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Tate Turner Prize Access Skill

This skill extracts comprehensive data about the Turner Prize from Tate's official website (tate.org.uk).

## Overview

The Turner Prize is one of the best-known visual arts prizes, awarded annually to a British artist. This skill provides access to:

- **Historical winners and nominees** (1984-present)
- **Artist details** with links to their Tate artist pages
- **2020 Bursary recipients** (special COVID-19 response)

## Functions

### 1. get_turner_prize_years

Get all Turner Prize years with nominees and winners.

**Parameters:**
- `start_year` (optional): Filter from this year (default: 1984)
- `end_year` (optional): Filter to this year (default: current year)

**Example:**
```json
{
  "function": "get_turner_prize_years",
  "start_year": 2010,
  "end_year": 2022
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "years": [
      {
        "year": 2022,
        "winner": null,
        "shortlisted": [
          "Heather Phillipson",
          "Ingrid Pollard",
          "Veronica Ryan",
          "Sin Wai Kin"
        ],
        "notes": ""
      },
      ...
    ],
    "total_years": 13,
    "years_with_nominees": 12,
    "source": "https://www.tate.org.uk/art/turner-prize"
  }
}
```

### 2. get_winners_grid

Get the visual winners grid with artist details and URLs to their Tate artist pages.

**Example:**
```json
{
  "function": "get_winners_grid"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "winners": [
      {
        "index": 1,
        "name": "Veronica Ryan OBE",
        "birth_year": "1956",
        "url": "https://www.tate.org.uk/art/artists/veronica-ryan-obe-2293",
        "full_text": "ARTIST\nVeronica Ryan OBE\nborn 1956"
      },
      ...
    ],
    "total": 29,
    "source": "https://www.tate.org.uk/art/turner-prize"
  }
}
```

### 3. get_bursary_recipients

Get the 2020 Turner Bursary recipients (awarded instead of the Turner Prize due to COVID-19).

**Example:**
```json
{
  "function": "get_bursary_recipients"
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "year": 2020,
    "recipients": [
      {
        "name": "Arika",
        "description": "Arika is a political arts organisation based in Edinburgh..."
      },
      {
        "name": "Liz Johnson Artur",
        "description": "Liz Johnson Artur is a Ghanaian-Russian photographer based in London..."
      },
      ...
    ],
    "total": 10,
    "intro": ["Due to the coronavirus pandemic, the jury of the cancelled 2020 Turner Prize..."],
    "source": "https://www.tate.org.uk/art/turner-prize/turner-bursaries"
  }
}
```

### 4. get_year_details

Get details for a specific Turner Prize year.

**Parameters:**
- `year` (required): The year to get details for

**Example:**
```json
{
  "function": "get_year_details",
  "year": 2019
}
```

**Returns:**
```json
{
  "success": true,
  "data": {
    "year": 2019,
    "winner": null,
    "shortlisted": [
      "Lawrence Abu Hamdan",
      "Helen Cammock",
      "Oscar Murillo",
      "Tai Shani"
    ],
    "notes": ""
  }
}
```

## Data Notes

- **Winner information**: The page structure lists shortlisted artists but doesn't explicitly mark winners in the year sections. The winners grid shows past winners visually.
- **2020**: Due to COVID-19, the Turner Prize was cancelled and replaced with bursaries to 10 artists.
- **Artist URLs**: The winners grid includes links to each artist's Tate page for additional information.
- **Year range**: Data available from 1984 (first Turner Prize) to present.

## Technical Details

- Uses Playwright browser automation for JavaScript-rendered content
- Extracts data from structured HTML with h3 year headings and unordered lists
- Handles special cases like the 2020 bursaries
- Provides both structured data and source URLs for verification

## Use Cases

- Research Turner Prize history and trends
- Find information about specific artists or years
- Analyze patterns in prize winners and nominees
- Get links to artist pages for deeper research
- Access information about the special 2020 bursary program
