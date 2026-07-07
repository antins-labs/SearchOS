# Bacardi Product Page Scraper

Extract product information from Bacardi rum product detail pages at www.bacardi.com.

## Overview

This skill provides access to product information on the Bacardi website, including:
- Product names
- Age (for aged rums like Reserva Ocho)
- ABV (Alcohol by Volume)
- Product descriptions

## ⚠️ Important: Cloudflare Protection

The Bacardi website is protected by Cloudflare's anti-bot system. This protection:

- Returns HTTP 403 status codes for automated requests
- Presents a JavaScript challenge that requires browser execution
- Blocks direct HTTP requests from automated tools

**When Cloudflare blocks access, the skill returns:**
```json
{
  "success": false,
  "error": "cloudflare_challenge",
  "is_cloudflare_challenge": true,
  "message": "The site is protected by Cloudflare. Direct HTTP access is blocked."
}
```

## Functions

### `list_products`

List known Bacardi rum product URLs.

**Parameters:** None

**Example:**
```python
result = await execute({'function': 'list_products'})
```

**Response:**
```json
{
  "success": true,
  "count": 3,
  "products": [
    {
      "name": "Reserva Ocho",
      "url": "https://www.bacardi.com/us/en/our-rums/reserva-ocho-rum/",
      "slug": "reserva-ocho-rum",
      "category": "aged_rum",
      "expected_age_years": 8
    },
    {
      "name": "Superior",
      "url": "https://www.bacardi.com/us/en/our-rums/superior-rum/",
      "slug": "superior-rum",
      "category": "white_rum"
    },
    {
      "name": "Gold",
      "url": "https://www.bacardi.com/us/en/our-rums/gold-rum/",
      "slug": "gold-rum",
      "category": "gold_rum"
    }
  ]
}
```

### `get_product`

Get detailed product information from a specific product page.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| url | string | Yes | Full URL of the product page |

**Example:**
```python
result = await execute({
    'function': 'get_product',
    'url': 'https://www.bacardi.com/us/en/our-rums/reserva-ocho-rum/'
})
```

**Success Response:**
```json
{
  "success": true,
  "url": "https://www.bacardi.com/us/en/our-rums/reserva-ocho-rum/",
  "name": "Reserva Ocho",
  "age_years": 8,
  "abv_percent": 40.0,
  "abv_text": "40% ABV",
  "description": "BACARDÍ Reserva Ocho is the ultimate sipping rum...",
  "product_type": "rum",
  "brand": "BACARDÍ"
}
```

**Error Response (Cloudflare blocked):**
```json
{
  "success": false,
  "error": "cloudflare_challenge",
  "url": "https://www.bacardi.com/us/en/our-rums/reserva-ocho-rum/",
  "is_cloudflare_challenge": true
}
```

## Extraction Methods

When access is successful, the skill uses multiple methods to extract product data:

1. **Meta Tags**: Title and description from `<meta>` tags
2. **JSON-LD**: Structured data in `<script type="application/ld+json">`
3. **Next.js Data**: `__NEXT_DATA__` script content
4. **HTML Parsing**: BeautifulSoup extraction from page content
5. **Regex Patterns**: ABV, age, and other numeric patterns
6. **URL Inference**: Product name from URL structure

### ABV Extraction Patterns

The skill looks for ABV in various formats:
- `40% ABV`
- `40% Alcohol`
- `ABV: 40%`
- `40% vol`
- `Alcohol 40%`

### Age Extraction Patterns

For aged rums, the skill detects:
- `8 Year Old`
- `Aged 8 Years`
- `8 Años`
- `Añejo 8`
- `Reserva 8`

## Errors

| Error Code | Description |
|------------|-------------|
| `cloudflare_challenge` | Site blocked by Cloudflare protection |
| `http_403` | HTTP 403 Forbidden (often Cloudflare) |
| `timeout` | Request timed out |
| `invalid_url` | URL not from www.bacardi.com domain |
| `missing_url` | URL parameter required for get_product |
| `unknown_function` | Invalid function name |

## Known Products

The following products have been identified:

| Product | URL | Category | Expected Age |
|---------|-----|----------|--------------|
| Reserva Ocho | /us/en/our-rums/reserva-ocho-rum/ | aged_rum | 8 years |
| Superior | /us/en/our-rums/superior-rum/ | white_rum | - |
| Gold | /us/en/our-rums/gold-rum/ | gold_rum | - |

## Dependencies

- `aiohttp>=3.8.0` - Async HTTP client
- `beautifulsoup4>=4.11.0` - HTML parsing

## Usage Notes

1. **Cloudflare Limitations**: Direct HTTP access to bacardi.com is likely blocked. Consider using a browser automation solution for real-world access.

2. **Rate Limiting**: Even without Cloudflare, respect rate limits and avoid overwhelming the server.

3. **URL Format**: URLs must start with `https://www.bacardi.com/`

4. **Regional Variations**: Product availability and specifications may vary by region. URLs are for the US English site (`/us/en/`).

## Testing

Run the test suite:

```python
import asyncio
from executor import execute

async def test():
    # Test listing products
    result = await execute({'function': 'list_products'})
    print(f"Found {result['count']} products")
    
    # Test getting a product (may be blocked by Cloudflare)
    result = await execute({
        'function': 'get_product',
        'url': 'https://www.bacardi.com/us/en/our-rums/reserva-ocho-rum/'
    })
    
    if result.get('is_cloudflare_challenge'):
        print("⚠️ Cloudflare blocked access")
    else:
        print(f"Product: {result.get('name')}")
        print(f"Age: {result.get('age_years')} years")
        print(f"ABV: {result.get('abv_percent')}%")

asyncio.run(test())
```

## Changelog

### v1.0.0 (2024-06-21)
- Initial implementation
- Support for list_products and get_product functions
- Cloudflare challenge detection and graceful error handling
- ABV and age extraction from multiple patterns
- JSON-LD and Next.js data parsing