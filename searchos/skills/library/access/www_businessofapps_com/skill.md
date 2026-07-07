# Business of Apps Data Extractor

Extracts structured app market data tables from [Business of Apps](https://www.businessofapps.com/data/), a comprehensive resource for app industry statistics, rankings, and market analysis.

## Overview

This skill fetches data tables containing:
- **Most Popular Apps**: Download rankings by platform (iOS, Android), category (social, games, entertainment, etc.), and time period
- **App Revenue**: Global app revenue statistics by year
- **Category Rankings**: Top apps in specific categories like social, games, music, shopping, etc.

## Available Functions

### fetch_page

Fetch all tables from a specific data page.

**Parameters:**
- `data_path` (string, required): Path to the data page

**Example:**
```python
{
    "function": "fetch_page",
    "data_path": "most-popular-apps"
}
```

**Returns:**
```python
{
    "success": true,
    "url": "https://www.businessofapps.com/data/most-popular-apps/",
    "tables": [
        {
            "id": "footable_92706",
            "title": "most popular apps",
            "columns": ["App", "Downloads (mm)"],
            "data": [
                {"App": "ChatGPT", "Downloads (mm)": "770"},
                {"App": "TikTok", "Downloads (mm)": "644"},
                ...
            ],
            "row_count": 15,
            "source_url": "..."
        },
        ...
    ],
    "table_count": 51,
    "total_rows": 500
}
```

### get_popular_apps

Get most popular apps tables, optionally filtered by category.

**Parameters:**
- `category` (string, optional): Category filter (e.g., 'social', 'games', 'music')

**Example:**
```python
{
    "function": "get_popular_apps",
    "category": "social"
}
```

**Returns:**
```python
{
    "success": true,
    "url": "https://www.businessofapps.com/data/most-popular-apps/",
    "tables": [
        {
            "id": "footable_79375",
            "title": "Most Popular Social Apps 2025",
            "columns": ["App", "Downloads (mm)"],
            "data": [
                {"App": "TikTok", "Downloads (mm)": "644"},
                {"App": "Instagram", "Downloads (mm)": "521"},
                ...
            ],
            "row_count": 10
        }
    ],
    "table_count": 1,
    "category_filter": "social"
}
```

### get_app_revenue

Get app revenue statistics.

**Example:**
```python
{
    "function": "get_app_revenue"
}
```

**Returns:**
```python
{
    "success": true,
    "url": "https://www.businessofapps.com/data/app-revenue/",
    "tables": [
        {
            "id": "footable_76578",
            "title": "App and game revenues 2016 to 2025 ($bn)",
            "columns": ["Year", "Revenue ($bn)"],
            "data": [
                {"Year": "2016", "Revenue ($bn)": "43.5"},
                {"Year": "2017", "Revenue ($bn)": "58.1"},
                ...
            ],
            "row_count": 10
        }
    ],
    "table_count": 1
}
```

### list_pages

List all available data pages on the site.

**Example:**
```python
{
    "function": "list_pages"
}
```

**Returns:**
```python
{
    "success": true,
    "pages": [
        {"name": "Benchmarks", "path": "app-benchmarks", "url": "..."},
        {"name": "Reports", "path": "app-reports", "url": "..."},
        {"name": "Sectors", "path": "app-sectors", "url": "..."},
        ...
    ],
    "page_count": 5
}
```

## Data Categories

Available categories for `get_popular_apps` include:
- **social** - Social networking apps (TikTok, Instagram, etc.)
- **games** - Mobile games
- **entertainment** - Entertainment apps (Spotify, Netflix, etc.)
- **music** - Music streaming and audio apps
- **shopping** - E-commerce apps (Amazon, Temu, etc.)
- **food** - Food delivery and restaurant apps
- **travel** - Travel and transportation apps
- **education** - Educational apps (Duolingo, etc.)
- **dating** - Dating apps (Tinder, Bumble, etc.)
- **health** - Health and fitness apps
- **finance** - Financial and payment apps
- **business** - Business and productivity apps
- **ai** - AI-powered apps (ChatGPT, etc.)

## Data Format

All table data is returned as structured arrays with:
- `id`: Unique table identifier
- `title`: Human-readable table title/category
- `columns`: Array of column names
- `data`: Array of row objects (keyed by column name)
- `row_count`: Number of data rows
- `source_url`: Original page URL

## Notes

- Data is scraped directly from rendered HTML tables
- Tables are powered by the Ninja Tables WordPress plugin
- Download numbers are in millions ("mm" suffix)
- Revenue figures are in billions USD
- Data is updated regularly by Business of Apps

## Error Handling

Returns structured error responses:
```python
{
    "success": false,
    "error": "HTTP 404",
    "url": "...",
    "tables": []
}
```

Common errors:
- Missing required parameters
- Invalid data path
- HTTP errors (timeout, 404, etc.)
- Network connectivity issues