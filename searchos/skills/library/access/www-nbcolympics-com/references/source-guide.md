# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# NBC Olympics Access Skill

This skill fetches content from the NBC Olympics website (nbcolympics.com), specializing in Olympic mascots data and article content extraction.

## Features

### 1. Olympic Mascots Gallery (`get_mascots`)

Retrieves comprehensive data about all Olympic mascots from 1968 to 2026, including:
- Year and season (Winter/Summer)
- Mascot name
- Description with historical context
- Associated image URL and alt text

**Example Usage:**
```json
// Get all mascots
{"function": "get_mascots"}

// Get Winter Olympics mascots only
{"function": "get_mascots", "season": "Winter"}

// Get mascots from 2024
{"function": "get_mascots", "year": 2024}

// Search for mascots with "bear" in name or description
{"function": "get_mascots", "search": "bear"}
```

**Response Structure:**
```json
{
  "success": true,
  "title": "A look back at Olympic mascots through the years",
  "url": "https://www.nbcolympics.com/news/look-back-olympic-mascots-through-years",
  "intro": "For every Olympic Games, there are a number of unique moments...",
  "mascots": [
    {
      "year": 2024,
      "season": "Summer",
      "name": "The Phryges",
      "description": "The personified Phrygian caps are representative of the French republic...",
      "image_url": "https://images.nbcolympics.com/...",
      "image_alt": "Paris 2024 Olympic Mascot"
    }
  ],
  "total_count": 29
}
```

### 2. Mascot by Year (`get_mascot_by_year`)

Get mascot(s) for a specific Olympic year.

**Example Usage:**
```json
// Get mascot for 1984
{"function": "get_mascot_by_year", "year": 1984}

// Get Winter Olympics mascot for 1984
{"function": "get_mascot_by_year", "year": 1984, "season": "Winter"}
```

**Note:** Some years have both Winter and Summer Olympics mascots (e.g., 1984, 1988, 1992, etc.).

### 3. Article Content (`get_article`)

Extracts full content from any NBC Olympics article URL, including:
- Title and meta description
- Author and publication date (when available)
- Full article text
- Images with alt text
- Document heading structure

**Example Usage:**
```json
{
  "function": "get_article",
  "url": "https://www.nbcolympics.com/news/look-back-olympic-mascots-through-years"
}
```

**Response Structure:**
```json
{
  "success": true,
  "title": "A look back at Olympic mascots through the years",
  "description": "In honor of Tina and Milo making their mascot debuts...",
  "author": null,
  "published_date": null,
  "url": "https://www.nbcolympics.com/news/...",
  "content": ["Paragraph 1...", "Paragraph 2..."],
  "content_text": "Full article text...",
  "images": [
    {"url": "https://...", "alt": "Image description"}
  ],
  "headings": [
    {"level": "h2", "text": "1968 Winter Olympics: Shuss"}
  ],
  "word_count": 593
}
```

## Data Coverage

### Olympic Mascots (1968-2026)
- **1968 Winter**: Shuss (Grenoble)
- **1972 Summer**: Waldi (Munich)
- **1976 Winter**: Schneemandl (Innsbruck)
- **1976 Summer**: Amik (Montreal)
- **1980 Winter**: Roni (Lake Placid)
- **1980 Summer**: Misha (Moscow)
- **1984 Winter**: Vučko (Sarajevo)
- **1984 Summer**: Sam (Los Angeles)
- ... and 21 more through 2026

## Error Handling

The skill returns structured error responses:
```json
{
  "error": "HTTP 404",
  "url": "https://www.nbcolympics.com/news/..."
}
```

Common errors:
- `HTTP 404`: Page not found
- `HTTP 403`: Access denied
- `URL parameter is required`: Missing URL for get_article
- `Year must be a valid integer`: Invalid year format
- `No mascot found for year X`: No mascot data for specified year

## Technical Notes

- Uses direct HTTP requests (no browser automation required)
- Parses HTML with BeautifulSoup
- Handles NBC Olympics' specific article structure
- Extracts high-resolution image URLs
- Cleans and structures content for easy consumption
