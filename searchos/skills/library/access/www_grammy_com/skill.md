# Grammy Awards Access Skill

This skill provides structured access to Grammy Awards data from the official grammy.com website.

## Features

### 1. Fetch Award Ceremony (`fetch_award_ceremony`)

Retrieve all categories and winners for a specific Grammy Awards ceremony.

**Parameters:**
- `url`: Grammy Awards ceremony URL (e.g., `https://www.grammy.com/awards/58th-annual-grammy-awards/`)

**Returns:**
```json
{
  "success": true,
  "ceremony_name": "58th annual grammy awards",
  "year": "2016",
  "year_info": "Honoring recordings released between Oct 1, 2014 – Sep 30, 2015",
  "total_categories": 84,
  "source_url": "https://www.grammy.com/awards/58th-annual-grammy-awards/",
  "categories": [
    {
      "category": "Record Of The Year",
      "category_url": "https://www.grammy.com/awards/categories/record-of-the-year/2016/",
      "winners": ["Mark Ronson", "Bruno Mars"],
      "work": "Uptown Funk"
    },
    // ... more categories
  ]
}
```

**Example URL patterns:**
- 38th Annual Grammy Awards (1996): `https://www.grammy.com/awards/38th-annual-grammy-awards/`
- 48th Annual Grammy Awards (2006): `https://www.grammy.com/awards/48th-annual-grammy-awards/`
- 58th Annual Grammy Awards (2016): `https://www.grammy.com/awards/58th-annual-grammy-awards/`

### 2. Fetch Category Details (`fetch_category_details`)

Retrieve detailed information about a specific Grammy category, including the winner and all nominees.

**Parameters:**
- `url`: Grammy category URL (e.g., `https://www.grammy.com/awards/categories/album-of-the-year/2016/`)

**Returns:**
```json
{
  "success": true,
  "category": "Album Of The Year",
  "year": "2016",
  "url": "https://www.grammy.com/awards/categories/album-of-the-year/2016/",
  "announcement": "Taylor Swift won the 2016 Grammy Award for Album Of The Year with \"1989\"",
  "description": "The Grammy Award for Album Of The Year recognizes...",
  "winner": {
    "work": "1989",
    "artists": ["Taylor Swift"],
    "credits": null
  },
  "nominees": [
    {
      "work": "Sound & Color",
      "artists": ["Alabama Shakes"],
      "credits": null
    },
    // ... more nominees
  ],
  "total_nominees": 4
}
```

**Example category URLs:**
- Record of the Year 2016: `https://www.grammy.com/awards/categories/record-of-the-year/2016/`
- Album of the Year 2016: `https://www.grammy.com/awards/categories/album-of-the-year/2016/`
- Best New Artist 2016: `https://www.grammy.com/awards/categories/best-new-artist/2016/`

### 3. Search Awards by Year (`search_awards_by_year`)

Find the Grammy Awards ceremony URL for a given year.

**Parameters:**
- `year`: The Grammy Awards year (telecast year, e.g., 2016 for the 58th Annual Grammy Awards)

**Returns:**
```json
{
  "found": true,
  "year": 2016,
  "ceremony_number": 58,
  "ceremony_url": "https://www.grammy.com/awards/58th-annual-grammy-awards/"
}
```

**Note:** Grammy Awards started in 1959 (1st Annual). The year parameter refers to the telecast year, not the eligibility year for recordings.

## Usage Notes

- Grammy Awards are numbered consecutively starting from 1959
- The year refers to the telecast year (e.g., 2016 Grammy Awards honored recordings from Oct 2014 - Sep 2015)
- Some categories may have multiple winners (e.g., producers, engineers)
- The `category_url` field in ceremony results can be used to fetch detailed nominee information

## Major Categories

The "Big Four" Grammy categories are:
- **Record of the Year**: Awarded to the performing artist, producer, and recording team
- **Album of the Year**: Awarded to the performing artist, producers, and recording team
- **Song of the Year**: Awarded to the songwriters
- **Best New Artist**: Awarded to a breakthrough artist

## Data Sources

All data is sourced from the official Grammy website: https://www.grammy.com/