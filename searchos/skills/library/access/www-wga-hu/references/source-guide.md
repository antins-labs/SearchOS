# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Web Gallery of Art (www.wga.hu) Access Skill

This skill provides programmatic access to the Web Gallery of Art, a comprehensive
virtual museum and searchable database of European fine arts from the 3rd to the
19th century (200-1900).

## Features

### Search Artworks
Search the database using multiple criteria:
- **Artist name**: Search by artist (partial match supported)
- **Title**: Search artwork titles
- **Time period**: Filter by century or specific periods
- **School/Movement**: Filter by art school (Italian, French, Dutch, etc.)
- **Art form**: Painting, sculpture, drawing, etc.
- **Type**: Religious, portrait, landscape, still life, etc.
- **Location**: Museum or collection name

### Get Artwork Details
Retrieve detailed information about a specific artwork:
- Title and artist information
- Creation date
- Medium and dimensions
- Current location (museum/collection)
- Catalogue numbers (e.g., F numbers for Van Gogh)
- Description and commentary
- High-resolution image URL

### Browse Gallery Collections
Browse curated gallery collections organized by artist and period:
- List all artworks in a collection
- Get thumbnail images and basic metadata
- Navigate between related collections

## Usage Examples

### Search for Monet's paintings
```json
{
  "function": "search",
  "author": "monet"
}
```

### Search for portraits from the 17th century
```json
{
  "function": "search",
  "type": "portrait",
  "time": "1601-1650"
}
```

### Get detailed information about Van Gogh's self-portrait
```json
{
  "function": "get_artwork",
  "url": "https://www.wga.hu/html_m/g/gogh_van/16/selfpo04a.html"
}
```

### Browse Van Gogh's self-portraits gallery
```json
{
  "function": "get_gallery",
  "url": "https://www.wga.hu/html_m/g/gogh_van/16/index.html"
}
```

### Paginated search results
```json
{
  "function": "search",
  "author": "rembrandt",
  "from_": 20,
  "max_": 20
}
```

## Response Structure

### Search Results
```json
{
  "success": true,
  "query": {...},
  "pagination": {
    "total_results": 200,
    "showing": 20,
    "start_index": 0,
    "per_page": 20,
    "has_more": true,
    "next_page_url": "..."
  },
  "results": [
    {
      "thumbnail": "https://www.wga.hu/art/...",
      "artist": "MONET, Claude",
      "title": "A Cart on the Snowy Road at Honfleur",
      "date": "1865",
      "medium": "Oil on canvas, 65 x 93 cm",
      "location": "Musée d'Orsay, Paris",
      "detail_page": "https://www.wga.hu/html/...",
      "artist_gallery": "https://www.wga.hu/html/..."
    }
  ]
}
```

### Artwork Details
```json
{
  "success": true,
  "artwork": {
    "url": "https://www.wga.hu/html_m/g/gogh_van/16/selfpo04a.html",
    "title": "Self-Portrait as a Painter",
    "artist_name": "GOGH, Vincent van",
    "artist_birth_year": 1853,
    "artist_birth_place": "Groot Zundert",
    "artist_death_year": 1890,
    "artist_death_place": "Auvers-sur-Oise",
    "date": "September-November 1886, Paris",
    "medium": "Oil on canvas, 47 x 39 cm",
    "location": "Van Gogh Museum, Amsterdam",
    "catalogue_numbers": "F 0181, JH 1090",
    "description": "This is one of the earliest self-portraits...",
    "image_url": "https://www.wga.hu/art/g/gogh_van/16/selfpo04a.jpg"
  }
}
```

## Notes

- The site uses ISO-8859-1 (latin-1) encoding, which this skill handles automatically
- Search supports partial matching for artist names and titles
- Gallery pages list all artworks in a specific collection with navigation to related collections
- Image URLs point to high-resolution versions suitable for download
- Some artworks may not have all fields populated (e.g., descriptions may be missing)

## Data Sources

All data is retrieved from the Web Gallery of Art (www.wga.hu), created by
Emil Krén and Daniel Marx. The site contains over 50,000 reproductions and
is an invaluable resource for art historical research.
