# ACI World Airport Rankings Access Skill

## Overview

This skill provides access to Airports Council International (ACI) World's airport traffic rankings, press releases, and statistics. ACI World is the trade association representing the world's airports, publishing authoritative data on passenger traffic, cargo volumes, and aircraft movements.

## Data Sources

### Primary Sources
- **Press Releases**: `https://aci.aero/news/` - Official announcements about ranking updates
- **Annual World Airport Traffic Dataset**: `https://store.aci.aero/` - Comprehensive paid dataset ($5,000 USD)
- **Preview Dataset**: Free demo Excel file available after form submission

### Data Coverage
- **Airports**: 2,800+ airports across 185+ countries
- **Categories**:
  - Passenger traffic (domestic and international)
  - Air cargo volumes (freight and mail)
  - Aircraft movements (operations)

## Functions

### 1. `list_press_releases`
Returns a list of recent press releases about airport rankings.

**Parameters:**
- `limit` (integer, optional): Maximum number of results (default: 20)

**Returns:**
```json
{
  "success": true,
  "data": {
    "articles": [
      {
        "title": "World's Busiest Airports Revealed in Final Global Rankings",
        "url": "https://aci.aero/2025/07/08/...",
        "date": "2025-07-08",
        "type": "press_release"
      }
    ],
    "total_found": 15
  }
}
```

### 2. `get_press_release`
Fetches full content from a specific press release.

**Parameters:**
- `url` (string, required): URL of the press release

**Returns:**
```json
{
  "success": true,
  "data": {
    "url": "https://aci.aero/...",
    "title": "World's Busiest Airports Revealed...",
    "date": "2025-07-08",
    "content": ["Paragraph 1...", "Paragraph 2..."],
    "highlights": {
      "total_passengers": "9.4 billion passengers",
      "growth_rates": ["8.4", "2.7"]
    },
    "images": [
      {
        "alt": "Table showing top 20 airports...",
        "url": "https://aci.aero/wp-content/uploads/..."
      }
    ],
    "related_links": [...]
  }
}
```

### 3. `get_ranking_data`
Extracts structured ranking information from press releases.

**Parameters:**
- `url` (string, optional): Specific press release URL (uses latest if not provided)

**Returns:**
```json
{
  "success": true,
  "data": {
    "source_url": "https://aci.aero/...",
    "title": "...",
    "date": "2025-07-08",
    "highlights": {
      "total_passengers": "9.4 billion passengers",
      "airport_count": "2,800 airports"
    },
    "key_findings": [
      "Shanghai Pudong (PVG) climbed 11 positions to rank 10th globally",
      "Guangzhou Baiyun (CAN) sustained its comeback, holding 12th place"
    ],
    "images": [
      {
        "alt": "Table showing top 20 airports...",
        "url": "..."
      }
    ],
    "data_source": {
      "text": "World Airport Traffic Dataset",
      "url": "https://store.aci.aero/..."
    }
  }
}
```

### 4. `download_preview`
Provides information about the preview dataset download.

**Returns:**
```json
{
  "success": true,
  "data": {
    "product_name": "Annual World Airport Traffic Dataset, 2025",
    "store_url": "https://store.aci.aero/...",
    "preview_download_url": "https://store.aci.aero/wp-content/uploads/.../WATR-Dataset-2025_Edition-Demo.xlsx",
    "full_dataset_price": "$5,000 USD (Regular)",
    "member_price": "$1,750 USD",
    "format": "Excel",
    "categories": ["Passengers", "Air Cargo", "Aircraft Movements"]
  }
}
```

### 5. `search_news`
Searches ACI World news articles by keywords.

**Parameters:**
- `keywords` (string, required): Search terms
- `limit` (integer, optional): Maximum results (default: 10)

## Important Notes

### Data Limitations
1. **Embedded Images**: Ranking tables are embedded as images, not text/HTML tables
2. **Paid Dataset**: Full data requires purchase ($5,000 USD for regular, $1,750 for members)
3. **Preview Available**: Free demo Excel file after form submission
4. **REST API Restricted**: WordPress REST API is blocked by iThemes Security

### Data Extraction Strategy
Since ranking tables are images, the skill:
- Extracts key findings mentioned in the text
- Provides URLs to the ranking table images
- Extracts statistics mentioned in the article text
- Links to the preview dataset download

### Key Statistics Available (from text)
- Total global passenger numbers
- Growth percentages
- Top 20 airport counts
- Notable ranking changes
- Year-over-year comparisons

## Typical Use Cases

1. **Get Latest Rankings**:
   ```
   function: get_ranking_data
   ```

2. **Find Specific Airport Information**:
   ```
   function: search_news
   keywords: "Dubai airport ranking"
   ```

3. **Get Dataset Download Info**:
   ```
   function: download_preview
   ```

4. **Browse All Press Releases**:
   ```
   function: list_press_releases
   limit: 20
   ```

## Technical Details

- **Base URL**: `https://aci.aero`
- **Store URL**: `https://store.aci.aero`
- **Content Type**: HTML (no JSON API available)
- **Rate Limiting**: Standard web scraping practices recommended
- **Authentication**: None required for public press releases

## Recent Example Data

From the 2024 rankings (published July 2025):
- Global passengers: 9.4 billion (+8.4% YoY)
- Top 20 airports handled: 1.54 billion passengers (16% of global traffic)
- Notable moves: Shanghai Pudong climbed to #10, Dubai jumped from #17 to #11
- US had 6 airports in top 20 (mostly domestic traffic, except JFK at 56% international)