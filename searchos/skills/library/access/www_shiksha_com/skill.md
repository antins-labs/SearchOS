# Shiksha.com University Rankings Skill

This skill fetches university ranking data from Shiksha.com, a popular education portal that aggregates rankings from major ranking bodies including QS World University Rankings, Times Higher Education (THE), US News & World Report, and more.

## Features

- **Comprehensive Rankings**: Extracts ranking tables from multiple ranking bodies:
  - QS World University Rankings (global and subject-specific)
  - Times Higher Education (THE) Rankings
  - US News & World Report Rankings
  - ARWU (Shanghai) Rankings
  - Financial Times Rankings
  - Bloomberg Rankings

- **University Comparisons**: Includes comparison tables with similar universities
- **Ranking Parameters**: Extracts detailed scoring breakdowns (Academic Reputation, Citations, Employer Reputation, etc.)
- **Historical Data**: Multiple years of ranking data when available

## Usage

### Get University Rankings

```json
{
  "function": "get_rankings",
  "country": "usa",
  "university_slug": "the-university-of-texas-at-austin"
}
```

Returns:
- University basic info (name, address, rating, logo)
- All ranking tables with categorization
- Key rankings extracted for quick access

### Get University Basic Info

```json
{
  "function": "get_university_info",
  "country": "uk",
  "university_slug": "university-of-oxford"
}
```

Returns basic university information from the main university page.

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `function` | Yes | `get_rankings` or `get_university_info` |
| `country` | Yes | Country code (lowercase): usa, uk, canada, australia, etc. |
| `university_slug` | Yes | University URL slug from Shiksha URLs |

## Finding the University Slug

The `university_slug` can be derived from the Shiksha URL:
- URL: `https://www.shiksha.com/studyabroad/usa/universities/massachusetts-institute-of-technology`
- Slug: `massachusetts-institute-of-technology`

## Output Structure

### Rankings Response

```json
{
  "success": true,
  "url": "https://www.shiksha.com/studyabroad/usa/universities/.../ranking",
  "university": {
    "name": "UT Austin",
    "url": "https://ww.utexas.edu/",
    "telephone": "512-475-7391",
    "address": "Austin, Texas 78712",
    "rating": "3.94",
    "review_count": "31"
  },
  "page_title": "The University of Texas at Austin Rankings 2026",
  "key_rankings": {
    "QS_2026": "68",
    "THE_2026": "50",
    ...
  },
  "tables": [
    {
      "type": "major_rankings",
      "headers": ["Ranking Body", "2023", "2024", "2025", "2026"],
      "rows": [["QS", "Not Ranked", "58", "66", "68"], ...]
    }
  ],
  "table_count": 23
}
```

### Table Types Detected

- `major_rankings`: Main QS/THE/US News rankings
- `subject_rankings`: Subject-specific rankings (Engineering, Business, etc.)
- `us_news_rankings`: US News detailed rankings
- `ranking_parameters`: Scoring breakdown (Academic Reputation, etc.)
- `university_comparison`: Comparison tables with peer institutions
- `the_parameters`: THE methodology parameters
- `bloomberg_parameters`: Bloomberg ranking indicators
- `methodology`: Ranking methodology weightage
- `unknown`: Uncategorized tables

## Notes

- Uses mobile user agent to bypass access restrictions
- Requires `Referer: https://www.shiksha.com/` header
- Data is extracted from HTML tables on the ranking page
- Historical corrections may appear as "Not Ranked" or "–"