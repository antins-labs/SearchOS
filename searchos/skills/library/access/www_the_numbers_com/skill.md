# The-Numbers.com Box Office Data Extractor

Fetch comprehensive movie box office and financial data from The-Numbers.com, one of the most trusted sources for movie industry financial information.

## Features

### 🎬 Movie Financial Data (`get_movie`)
Get detailed financial metrics for any movie:

- **Box Office Figures**: Domestic, international, and worldwide gross
- **Production Budget**: Film production costs
- **Opening Weekend**: Opening weekend box office performance
- **Weekly Performance**: Detailed weekly box office breakdown with rank, gross, theaters, and totals
- **Additional Info**: MPAA rating, runtime, franchises, release dates, distributor

**Example:**
```json
{
  "function": "get_movie",
  "movie_title": "Avengers: Endgame",
  "year": 2019
}
```

Returns:
```json
{
  "success": true,
  "title": "Avengers: Endgame",
  "year": 2019,
  "domestic_box_office": 858373000,
  "international_box_office": 1859130922,
  "worldwide_box_office": 2717503922,
  "production_budget": 400000000,
  "opening_weekend": 357115007,
  "franchises": ["Marvel Cinematic Universe", "Avengers"],
  "mpaa_rating": "PG-13",
  "running_time_minutes": 181
}
```

### 🎭 Franchise Data (`get_franchise`)
Get all movies in a franchise with their financial data:

- Complete list of franchise movies (released and upcoming)
- Financial totals for the entire franchise
- Individual movie budgets and box office

**Example:**
```json
{
  "function": "get_franchise",
  "franchise_name": "Marvel Cinematic Universe"
}
```

Returns all MCU movies with their financials and calculates total worldwide box office.

### 📊 Box Office Charts (`get_box_office_chart`)
Get current or historical box office rankings:

- **Weekend Chart**: Top movies by weekend gross
- **Daily Chart**: Daily box office performance
- **Weekly Chart**: Weekly aggregated performance
- **Historical Data**: View charts from specific dates

**Example:**
```json
{
  "function": "get_box_office_chart",
  "chart_type": "weekend"
}
```

Or for historical:
```json
{
  "function": "get_box_office_chart",
  "chart_type": "daily",
  "date": "2024-06-15"
}
```

## URL Patterns

If you know the exact URL, you can bypass title parsing:

- **Movies**: `https://www.the-numbers.com/movie/Movie-Name-(Year)`
  - Example: `https://www.the-numbers.com/movie/Avatar-(2009)`

- **Franchises**: `https://www.the-numbers.com/movies/franchise/Franchise-Name`
  - Example: `https://www.the-numbers.com/movies/franchise/Star-Wars`

## Data Notes

- All monetary values are parsed to integers (e.g., `$1,234,567` → `1234567`)
- Raw string values are also preserved (e.g., `worldwide_box_office_raw`)
- Zero values (`$0`) may indicate unreleased movies or missing data
- The site returns the homepage (404 behavior) for invalid movie/franchise names

## Supported Franchises

Popular franchises available include:
- Marvel Cinematic Universe
- Star Wars
- Harry Potter / Wizarding World
- DC Extended Universe
- James Bond
- Fast & Furious
- Jurassic Park
- And many more...

## Limitations

- Person pages (actors, directors) are not supported as they're not reliably accessible
- Search functionality requires browser interaction; use exact titles or URLs when possible
- Some independent/limited release movies may have incomplete data

## Data Source

All data is sourced from [The-Numbers.com](https://www.the-numbers.com), a leading provider of movie industry financial data serving studios, investors, and industry professionals since 1997.