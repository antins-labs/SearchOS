# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Art Gallery of NSW - Prizes Access Skill

This skill retrieves artwork and artist information from the Art Gallery of NSW's prestigious art prize competitions.

## Supported Prizes

- **Archibald Prize** - Australia's most prestigious portrait prize
- **Wynne Prize** - For landscape painting or figure sculpture
- **Sulman Prize** - For subject painting, genre painting, or mural project

## Functions

### get_prize_year

Get all artworks (winners and finalists) for a specific prize year.

**Parameters:**
- `prize` (string): Prize name - "archibald", "wynne", or "sulman" (default: "archibald")
- `year` (string): Year, e.g., "2023" (default: "2023")

**Returns:**
- Winners with award information
- Complete list of finalists with artist, title, thumbnail URL, and artwork ID
- Total count of artworks

**Example:**
```json
{
  "function": "get_prize_year",
  "prize": "archibald",
  "year": "2023"
}
```

### get_artwork

Get detailed information about a specific artwork.

**Parameters:**
- `artwork_id` (string, required): The artwork ID (found in prize year listings)
- `prize` (string): Prize name (default: "archibald")
- `year` (string): Year (default: "2023")

**Returns:**
- Artist name
- Artwork title
- Medium (e.g., "oil on linen")
- Dimensions
- Image URL
- Description/artist statement (when available)
- Award information (if winner)

**Example:**
```json
{
  "function": "get_artwork",
  "artwork_id": "30531",
  "prize": "archibald",
  "year": "2023"
}
```

### get_gallery_labels

Get in-gallery label information for a prize year (simplified view with numbered entries).

**Parameters:**
- `prize` (string): Prize name (default: "archibald")
- `year` (string): Year (default: "2023")

**Returns:**
- Ordered list of artworks as displayed in gallery
- Artist and title for each artwork
- Artwork IDs for detailed lookups

**Example:**
```json
{
  "function": "get_gallery_labels",
  "prize": "archibald",
  "year": "2023"
}
```

### list_prize_years

List all available years for a specific prize.

**Parameters:**
- `prize` (string): Prize name (default: "archibald")

**Returns:**
- List of available years with URLs
- Sorted in descending order (most recent first)

**Example:**
```json
{
  "function": "list_prize_years",
  "prize": "archibald"
}
```

## Data Sources

All data is retrieved from the official Art Gallery of NSW website:
- Prize listings: `https://www.artgallery.nsw.gov.au/prizes/{prize}/{year}/`
- Artwork details: `https://www.artgallery.nsw.gov.au/prizes/{prize}/{year}/{artwork_id}/`
- Gallery labels: `https://www.artgallery.nsw.gov.au/in-gallery/aws{YY}-labels/{prize}-{year}/`

## Notes

- The Archibald Prize data is available from 1921 onwards
- Not all years may have complete digital records
- In-gallery label pages may only be available for recent years
- Artwork IDs are unique within a prize year but may differ across years
