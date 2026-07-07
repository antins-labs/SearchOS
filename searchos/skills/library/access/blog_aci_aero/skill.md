# ACI World Airport Rankings Access Skill

This skill fetches airport traffic rankings from ACI World (Airports Council International), the authoritative source for global airport statistics.

## Overview

ACI World publishes annual airport traffic rankings covering:
- **Total passenger traffic** - Top airports by total passengers
- **International passengers** - Top airports by international passenger volume
- **Cargo volume** - Top airports by freight/mail tonnes
- **Aircraft movements** - Top airports by flight operations

The data covers over 2,800 airports across 185+ countries and territories.

## Available Functions

### `get_rankings`
Get airport ranking data for Top 5 airports.

**Parameters:**
- `category` (optional): `passengers`, `cargo`, `international`, or `all` (default: `all`)

**Example:**
```python
params = {
    "function": "get_rankings",
    "category": "passengers"
}
```

**Returns:** Top 5 airports in specified category with rank, airport name, IATA code, and country.

### `get_statistics`
Get key global airport traffic statistics for 2024.

**Example:**
```python
params = {"function": "get_statistics"}
```

**Returns:**
- Total global passengers (9.4 billion, +8.4% YoY)
- Total cargo volume (127M metric tonnes, +9.9% YoY)
- Total aircraft movements (100.6M, +3.9% YoY)
- Notable highlights and trends

### `get_article`
Fetch the full ACI World article with rankings analysis.

**Parameters:**
- `url` (optional): Article URL (default: 2024 rankings article)

**Example:**
```python
params = {"function": "get_article"}
```

**Returns:** Article title, description, metadata, full content paragraphs, and links to ranking tables.

### `get_ranking_tables`
Get URLs for ranking table images (PNG format, Top 20 tables).

**Parameters:**
- `category` (optional): Specific category or all tables

**Example:**
```python
params = {"function": "get_ranking_tables", "category": "cargo"}
```

**Returns:** Image URLs and descriptions for:
- Total Passengers (Top 20)
- Cargo Volume (Top 20)
- Aircraft Movements (Top 20)
- International Passengers (Top 20)

### `search_airport`
Search for a specific airport in the rankings.

**Parameters:**
- `query` (required): Airport name, IATA code, or country

**Example:**
```python
params = {"function": "search_airport", "query": "Dubai"}
```

**Returns:** Matching airports with their rankings across categories.

### `get_all`
Get all available data in one call.

**Example:**
```python
params = {"function": "get_all"}
```

**Returns:** Combined data from all functions including article, rankings, statistics, and image URLs.

## 2024 Key Findings

1. **Atlanta (ATL)** maintains #1 position for total passengers
2. **Passenger traffic** recovered to 9.4B (+2.7% vs 2019 pre-pandemic)
3. **Shanghai Pudong (PVG)** climbed 11 places into Top 10
4. **Dubai (DXB)** leads international passengers and jumped 6 places in cargo
5. **Hong Kong (HKG)** leads cargo volume
6. **North America** dominates across all three categories

## Data Sources

- **Article:** https://blog.aci.aero/airport-economics/busiest-airports-in-the-world-2024/
- **Full Dataset:** Available for purchase at ACI World Store (link provided in results)
- **Ranking Tables:** High-resolution PNG images with detailed Top 20 breakdowns

## Notes

- Top 5 rankings are embedded in the article text
- Detailed Top 20 rankings are available as PNG table images
- For complete data (2,800+ airports), the ACI World Airport Traffic Dataset must be purchased

## Example Usage

```python
# Get all rankings
result = await execute({"function": "get_rankings"})

# Search for an airport
result = await execute({"function": "search_airport", "query": "LHR"})

# Get statistics
result = await execute({"function": "get_statistics"})

# Get ranking table images
result = await execute({"function": "get_ranking_tables"})
```