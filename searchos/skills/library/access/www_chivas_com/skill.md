# Chivas Regal Product Data Skill

## Overview

This skill extracts detailed product information from Chivas Regal whisky product pages at www.chivas.com. Due to Cloudflare protection on the live site, data is retrieved from Internet Archive snapshots.

## Supported Products

| Slug | Name | Age Statement |
|------|------|---------------|
| `chivas-12` | Chivas 12 Year Old | 12 years |
| `chivas-18` | Chivas 18 Year Old | 18 years |
| `chivas-25` | Chivas 25 Year Old | 25 years |

## Functions

### list_products

Returns a list of all available products with basic information.

```python
result = await execute({"function": "list_products"})
```

**Response:**
```json
{
  "products": [
    {
      "slug": "chivas-12",
      "name": "Chivas 12",
      "age": 12,
      "url": "https://www.chivas.com/en-us/collection/chivas-12/"
    },
    ...
  ],
  "total": 3
}
```

### get_product

Fetches detailed information for a specific product.

```python
result = await execute({
    "function": "get_product",
    "slug": "chivas-12"
})
```

**Parameters:**
- `slug` (required): Product identifier (`chivas-12`, `chivas-18`, or `chivas-25`)
- `use_archive` (optional): Use Internet Archive (default: `true`)

**Response:**
```json
{
  "slug": "chivas-12",
  "url": "https://www.chivas.com/en-us/collection/chivas-12/",
  "source_url": "https://web.archive.org/web/2023/...",
  "brand": "Chivas Regal",
  "category": "Blended Scotch Whisky",
  "name": "Chivas 12",
  "description": "With notes of rich sultanas and touches of warm cinnamon.",
  "full_description": "Chivas Regal 12 Year Old Blended Scotch whisky...",
  "age_statement": 12,
  "image_url": "https://www.chivas.com/wp-content/uploads/...",
  "rating": {
    "value": 4.5,
    "count": 538
  },
  "tasting_notes": {
    "nose": "Wild herbs, heather, honey & orchard fruits",
    "palate": "Round & creamy with honey, vanilla, hazelnut & butterscotch",
    "finish": "Warm and lingering"
  },
  "data_source": "internet_archive"
}
```

### get_all_products

Fetches detailed information for all products.

```python
result = await execute({"function": "get_all_products"})
```

## Extracted Data Fields

| Field | Description |
|-------|-------------|
| `name` | Product name from JSON-LD |
| `description` | Short description from JSON-LD |
| `full_description` | Longer description from meta tags |
| `brand` | Always "Chivas Regal" |
| `category` | Always "Blended Scotch Whisky" |
| `age_statement` | Age in years (12, 18, or 25) |
| `tasting_notes.nose` | Aroma profile |
| `tasting_notes.palate` | Taste profile |
| `tasting_notes.finish` | Aftertaste profile |
| `rating.value` | Average rating (out of 5) |
| `rating.count` | Number of reviews |
| `image_url` | Product image URL |
| `abv_percent` | Alcohol by volume (if available) |

## Data Source

The live Chivas website (www.chivas.com) is protected by Cloudflare Turnstile bot detection, making direct scraping unreliable. This skill retrieves product data from Internet Archive snapshots dated 2024, which contain the complete product pages with structured JSON-LD data.

## Example Usage

```python
# List all products
products = await execute({"function": "list_products"})

# Get specific product
chivas_12 = await execute({
    "function": "get_product",
    "slug": "chivas-12"
})

# Get all products with full details
all_products = await execute({"function": "get_all_products"})
```

## Error Handling

The skill returns structured error responses rather than raising exceptions:

```json
{
  "error": "Unknown product slug: chivas-15",
  "valid_slugs": ["chivas-12", "chivas-18", "chivas-25"]
}
```

## Rate Limiting

To be respectful to the Internet Archive, this skill implements reasonable delays between requests. The recommended rate is 2 requests per second.