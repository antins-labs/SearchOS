# G.E.M. (I Am Gem) Tour Data Extractor

This skill extracts concert tour information from G.E.M.'s official website (www.iamgem.com), providing structured access to her complete touring history across multiple world tours.

## Available Tours

The website contains data for the following tours:

1. **I AM GLORIA 世界巡迴演唱會** (2024-2026)
   - Latest world tour with dates across Asia, North America, and Europe
   - 59 concert dates

2. **Queen of Hearts 世界巡迴演唱會** (2017-2019)
   - 38 concert dates across Asia, Australia, and North America

3. **G.E.M. X.X.X. Live 世界巡迴演唱會** (2014-2015)
   - 52 concert dates worldwide

4. **G.E.M. Get Everybody Moving 世界巡迴演唱會** (2011-2012)
   - 10 concert dates

## Functions

### list_tours
List all available tour names with their date counts.

```json
{
  "function": "list_tours"
}
```

### get_tours
Get full tour data. Can be filtered by tour name or year.

**Get all tours:**
```json
{
  "function": "get_tours"
}
```

**Filter by tour name:**
```json
{
  "function": "get_tours",
  "tour_name": "GLORIA"
}
```

**Filter by year:**
```json
{
  "function": "get_tours",
  "year": 2025
}
```

### search_by_city
Search concerts by city name (partial match).

```json
{
  "function": "search_by_city",
  "city": "上海"
}
```

### search_by_year
Search concerts by year.

```json
{
  "function": "search_by_year",
  "year": 2024
}
```

### search_by_venue
Search concerts by venue name (partial match).

```json
{
  "function": "search_by_venue",
  "venue": "紅磡"
}
```

### get_statistics
Get overall tour statistics including unique cities, venues, and years spanned.

```json
{
  "function": "get_statistics"
}
```

## Response Format

All responses follow this structure:

```json
{
  "success": true,
  "error": null,
  "total_tours": 4,
  "total_dates": 159,
  "tours": [
    {
      "tour_name": "I AM GLORIA世界巡迴演唱會",
      "date_count": 59,
      "dates": [
        {
          "date": "2025/12/26-28、31,2026/1/3-4、9、11-13",
          "city": "廣州",
          "venue": "廣東省奧林匹克體育中心體育場",
          "years": [2025, 2026]
        }
      ]
    }
  ],
  "statistics": {
    "unique_cities": 60,
    "unique_venues": 65,
    "years_span": "2011 - 2026",
    "available_years": [2026, 2025, 2024, ..., 2011]
  }
}
```

## Notes

- The site is in Chinese (Traditional/Simplified), but venue names for international locations may be in English
- Date formats follow the pattern: `YYYY/M/D` or `YYYY/M/D - M/D` for date ranges
- Some dates span multiple shows (e.g., `2025/12/26-28` means December 26-28)
- International cities are shown with both Chinese and English names (e.g., "加拿大多倫多" for Toronto, Canada)