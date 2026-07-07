# Dongchedi (懂车帝) Access Skill

This skill provides access to car sales rankings and articles from [dongchedi.com](https://www.dongchedi.com), one of China's leading automotive information platforms owned by ByteDance.

## Features

### 1. Sales Rankings (get_sales_ranking)

Fetch car sales rankings with detailed information including:
- Vehicle name and brand
- Sales count and ranking position
- Price range
- Brand and sub-brand information
- Energy type (ICE/EV/PHEV/etc.)

**Types of rankings available:**
- `sale` - All vehicles (default)
- `energy` - New energy vehicles only (EVs, PHEVs, etc.)

**Example output:**
```
Top 10 cars (All Sales):
1. 星愿 (Geely Galaxy) - 5.98-9.18万 - Sales: 38,751
2. Model Y (Tesla) - 26.35-31.35万 - Sales: 28,911
3. 小米SU7 (Xiaomi) - 21.99-30.39万 - Sales: 24,023
...
```

### 2. Article Content (get_article)

Fetch automotive articles by ID, including:
- Article title and content (HTML format)
- Publication time
- Author information
- View/like/comment statistics
- Related car series mentioned

**Note:** Some articles may require JavaScript rendering and might not be fully accessible.

## Usage Examples

### Get all car sales ranking
```json
{
  "function": "get_sales_ranking",
  "ranking_type": "sale"
}
```

### Get new energy vehicle sales ranking
```json
{
  "function": "get_sales_ranking",
  "ranking_type": "energy"
}
```

### Get article content
```json
{
  "function": "get_article",
  "article_id": "7583347830648078873"
}
```

## Data Source

This skill extracts data from the Next.js server-side rendered `__NEXT_DATA__` script tag embedded in dongchedi.com's HTML pages. This approach provides structured JSON data without the need for browser automation.

## Returned Data Structure

### Sales Ranking
- `condition`: Filter conditions applied (type, city, etc.)
- `paging`: Pagination info (count, has_more, offset, total)
- `cars`: Array of car objects with:
  - `series_id`, `series_name`: Vehicle identifiers
  - `brand_id`, `brand_name`: Brand information
  - `rank`, `last_rank`: Ranking position
  - `sales_count`: Monthly sales volume
  - `price`, `min_price`, `max_price`: Price range in 10k CNY
  - `image`: Vehicle image URL
  - `energy_type`: Fuel type indicator

### Article
- `article_id`: Article identifier
- `title`: Article title
- `content_html`: Full content in HTML
- `publish_time`: Timestamp
- `author`: Author info
- `stats`: Views, comments, likes
- `related_series`: Car models mentioned

## Limitations

1. Articles may not always be accessible via direct HTTP fetch due to anti-bot measures
2. Sales data is monthly and may lag by 1-2 months
3. Default returns top 10 vehicles; pagination not currently supported
4. City-specific rankings default to Beijing

## Technical Notes

- Uses `aiohttp` for async HTTP requests
- Parses HTML with BeautifulSoup
- Extracts JSON from `__NEXT_DATA__` script tag (Next.js SSR pattern)
- No authentication required for public ranking pages