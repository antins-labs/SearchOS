# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Kroger.com Product Access Skill

This skill retrieves product information from Kroger.com product pages, handling anti-bot protections through browser automation.

## Features

- **Product Page Fetching**: Retrieve detailed product information by URL or UPC
- **Product Search**: Search for products on Kroger.com
- **Anti-Bot Handling**: Uses browser automation with realistic fingerprinting to bypass protections
- **Structured Data Extraction**: Returns clean, structured product data

## Functions

### get_product

Fetch a single product's detailed information.

**Parameters:**
- `url` (string): Full Kroger product page URL
- `upc` (string): Product UPC code (alternative to URL)

**Example:**
```json
{
  "function": "get_product",
  "url": "https://www.kroger.com/p/simple-truth-organic-kombucha-ginger/0001111087699"
}
```

Or by UPC:
```json
{
  "function": "get_product",
  "upc": "0085707500712"
}
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.kroger.com/p/...",
  "source": "kroger.com",
  "name": "Simple Truth Organic Kombucha Ginger",
  "brand": "Simple Truth Organic",
  "upc": "0001111087699",
  "price": {
    "current": 3.99,
    "regular": 4.29
  },
  "size": "16 oz",
  "description": "Product description...",
  "images": ["https://..."],
  "availability": "In Stock"
}
```

### search_products

Search for products on Kroger.com.

**Parameters:**
- `query` (string): Search query

**Example:**
```json
{
  "function": "search_products",
  "query": "organic kombucha"
}
```

**Returns:**
```json
{
  "success": true,
  "query": "organic kombucha",
  "url": "https://www.kroger.com/search?query=...",
  "count": 15,
  "products": [
    {
      "name": "Product Name",
      "brand": "Brand",
      "upc": "0001111087699",
      "url": "https://www.kroger.com/p/...",
      "price": {"current": 3.99},
      "image": "https://..."
    }
  ]
}
```

## Error Handling

The skill returns structured error responses:

```json
{
  "success": false,
  "error": "Access blocked (403 Forbidden) - anti-bot protection triggered",
  "error_type": "HTTPStatusError"
}
```

Common errors:
- **403 Forbidden**: Anti-bot protection triggered; may need retry
- **404 Not Found**: Product not found
- **Timeout**: Page took too long to load

## Technical Details

The skill uses Playwright browser automation with:
- Realistic browser fingerprint (Chrome on macOS)
- JavaScript rendering for dynamic content
- Anti-detection scripts to hide automation markers
- Proper HTTP headers including sec-ch-ua and sec-fetch headers
- Geolocation set to a Kroger service area (Columbus, OH)

Data extraction prioritizes:
1. Next.js `__NEXT_DATA__` for structured product data
2. Visible page elements with data-qa attributes
3. Fallback selectors for generic product elements

## Limitations

- Requires JavaScript rendering (slower than direct API calls)
- May encounter rate limiting with rapid successive requests
- Product availability is location-dependent
- Prices may vary by store location
