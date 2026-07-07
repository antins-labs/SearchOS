# Spotify Newsroom Wrapped Data Extractor

## Overview

This skill extracts Spotify Wrapped ranking data from Spotify's official newsroom website (newsroom.spotify.com). It provides structured access to annual top charts including artists, songs, albums, podcasts, and audiobooks.

## Supported Data

### Years
- **2024**: Full Wrapped data with global and US rankings
- **2023**: Full Wrapped data with global and US rankings

### Categories
| Category | Description | Example |
|----------|-------------|---------|
| `artists` | Most-streamed artists | Taylor Swift, The Weeknd, Bad Bunny |
| `songs` | Most-streamed songs | "Espresso" by Sabrina Carpenter |
| `albums` | Most-streamed albums | THE TORTURED POETS DEPARTMENT by Taylor Swift |
| `podcasts` | Top podcasts | The Joe Rogan Experience, Call Her Daddy |
| `audiobooks` | Top audiobooks on Premium | A Court of Thorns and Roses |
| `viral_songs` | Most-viral songs globally | "Die With A Smile" by Bruno Mars, Lady Gaga |
| `anticipated_podcasts` | Most-anticipated podcast launches (US only) | Mind the Game with LeBron James |

### Regions
- `global`: Worldwide rankings
- `us`: United States specific rankings

## Functions

### `get_wrapped`
Get all ranking data for a specific year.

**Parameters:**
- `year` (string, optional): "2023" or "2024". Default: "2024"

**Example:**
```json
{
  "function": "get_wrapped",
  "year": "2024"
}
```

**Response:**
```json
{
  "url": "https://newsroom.spotify.com/...",
  "title": "Revealed: The Top Artists, Songs, Albums...",
  "year": "2024",
  "sections": [
    {
      "heading": "Most-Streamed Artists Globally in 2024",
      "category": "artists",
      "region": "global",
      "content_type": "artist",
      "items": [
        {"rank": 1, "name": "Taylor Swift"},
        {"rank": 2, "name": "The Weeknd"},
        ...
      ],
      "count": 10
    },
    ...
  ],
  "section_count": 12
}
```

---

### `get_all`
Get Wrapped data for all available years.

**Parameters:** None

**Example:**
```json
{
  "function": "get_all"
}
```

---

### `search`
Search within rankings with filters.

**Parameters:**
- `year` (string, optional): "2023" or "2024". Default: "2024"
- `category` (string, optional): Filter by category
- `region` (string, optional): Filter by "global" or "us"
- `query` (string, optional): Text search query
- `limit` (integer, optional): Max results per section. Default: 10

**Example: Find all entries containing "Taylor":**
```json
{
  "function": "search",
  "year": "2024",
  "query": "Taylor"
}
```

**Example: Get global songs:**
```json
{
  "function": "search",
  "year": "2024",
  "category": "songs",
  "region": "global"
}
```

---

### `get_top`
Get top N entries for a specific category and region.

**Parameters:**
- `year` (string, optional): "2023" or "2024". Default: "2024"
- `category` (string, optional): Category to fetch. Default: "songs"
- `region` (string, optional): "global" or "us". Default: "global"
- `n` (integer, optional): Number of entries. Default: 10

**Example: Get top 5 global songs:**
```json
{
  "function": "get_top",
  "year": "2024",
  "category": "songs",
  "region": "global",
  "n": 5
}
```

**Response:**
```json
{
  "year": "2024",
  "category": "songs",
  "region": "global",
  "heading": "Most-Streamed Songs Globally",
  "top_n": [
    {"rank": 1, "title": "Espresso", "artist": "Sabrina Carpenter", "raw": "\"Espresso\" by Sabrina Carpenter"},
    {"rank": 2, "title": "Beautiful Things", "artist": "Benson Boone", "raw": "\"Beautiful Things\" by Benson Boone"},
    {"rank": 3, "title": "BIRDS OF A FEATHER", "artist": "Billie Eilish", "raw": "\"BIRDS OF A FEATHER\" by Billie Eilish"},
    {"rank": 4, "title": "Gata Only", "artist": "FloyyMenor, Cris Mj", "raw": "\"Gata Only\" by FloyyMenor, Cris Mj"},
    {"rank": 5, "title": "Lose Control", "artist": "Teddy Swims", "raw": "\"Lose Control\" by Teddy Swims"}
  ],
  "count": 5,
  "total_in_section": 10
}
```

## Use Cases

1. **Music Industry Analysis**: Track top artists, songs, and albums year over year
2. **Podcast Research**: Identify top-performing podcasts globally and in the US
3. **Audiobook Trends**: Discover popular audiobooks among Spotify Premium subscribers
4. **Regional Comparisons**: Compare global vs US listening trends
5. **Artist Search**: Find if specific artists appeared in any yearly rankings

## Data Quality

- Data is sourced directly from Spotify's official newsroom announcements
- Rankings are released annually as part of Spotify Wrapped
- Content is static once published (no dynamic updates)
- Suitable for caching (recommended TTL: 24 hours)

## Technical Notes

- Access method: HTTP scraping with BeautifulSoup
- No API key required
- Rate limit: 2 requests per second recommended
- All data is publicly available on newsroom.spotify.com