# Smirnoff Product Access Skill

Access product information from www.smirnoff.com including vodka, flavored spirits, and ready-to-drink products.

## Overview

This skill provides access to the Smirnoff product catalog by scraping product pages directly. The site uses Next.js with server-side rendering and embeds product data as JSON-LD Product schema, making it easily accessible via direct HTTP requests.

## Functions

### get_product

Get detailed information about a specific product by URL.

**Parameters:**
- `url` (string, required): Full URL of the product page
- `locale` (string, optional): Locale code (default: "en-us")

**Example:**
```python
result = await execute({
    "function": "get_product",
    "url": "https://www.smirnoff.com/en-us/products/vodkas-and-flavors/smirnoff-no-21-vodka"
})
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.smirnoff.com/en-us/products/vodkas-and-flavors/smirnoff-no-21-vodka",
  "name": "Smirnoff No. 21 Vodka",
  "title": "Smirnoff 21 Vodka | Classic Vodkas | Smirnoff",
  "description": "Introducing the No.1 Vodka in the world. Our triple distilled and 10 times filtered vodka...",
  "image": "https://images.ctfassets.net/tlircn1cnxbm/...",
  "brand": "Smirnoff Rebuild",
  "categories": ["Classic Vodka", "Popular Products"],
  "sku": "0082000000068",
  "mpn": "67644eb72d14db0ed139e22e",
  "abv": "40%",
  "sizes": ["750ML"],
  "disclaimer": "SMIRNOFF No. 21 Vodka. Distilled From Grain. 40% Alc/Vol."
}
```

### get_products

Get multiple products by their URLs in a single request.

**Parameters:**
- `urls` (array, required): List of product page URLs

**Example:**
```python
result = await execute({
    "function": "get_products",
    "urls": [
        "https://www.smirnoff.com/en-us/products/vodkas-and-flavors/smirnoff-no-21-vodka",
        "https://www.smirnoff.com/en-us/products/vodkas-and-flavors/smirnoff-no-57-vodka"
    ]
})
```

### list_products

List all products or products in a specific category.

**Parameters:**
- `category` (string, optional): Product category filter
- `locale` (string, optional): Locale code (default: "en-us")

**Example:**
```python
# List all products
result = await execute({
    "function": "list_products"
})

# List products in a specific category
result = await execute({
    "function": "list_products",
    "category": "vodkas-and-flavors"
})
```

**Returns:**
```json
{
  "success": true,
  "url": "https://www.smirnoff.com/en-us/products",
  "product_count": 79,
  "products": [
    {
      "url": "https://www.smirnoff.com/en-us/products/ready-to-drink/ice-grape",
      "slug": "ice-grape"
    },
    ...
  ]
}
```

### search_products

Search products by name or keyword (matches against product URL/slug).

**Parameters:**
- `query` (string, required): Search query
- `locale` (string, optional): Locale code (default: "en-us")

**Example:**
```python
result = await execute({
    "function": "search_products",
    "query": "ice"
})
```

## Product Categories

The site organizes products into the following categories:
- `vodkas-and-flavors` - Classic and flavored vodkas
- `ready-to-drink` - Smirnoff Ice and other RTD products
- `flavored-vodkas` - Flavored vodka variants
- `classic-vodkas` - Traditional vodka offerings

## Data Extraction

Product data is extracted from:

1. **JSON-LD Product Schema**: The primary source for product information, embedded in the page HTML
   - `name`: Product name
   - `description`: Product description
   - `image`: Product image URL
   - `brand`: Brand name
   - `category`: Product categories
   - `sku`: Stock keeping unit
   - `mpn`: Manufacturer part number

2. **Meta Tags**: Additional SEO metadata
   - `description`: SEO description
   - `og:title`, `og:description`: Open Graph data
   - `twitter:title`, `twitter:description`: Twitter card data

3. **Pattern Matching**: Additional data not in schema
   - ABV (Alcohol By Volume): Extracted from page content
   - Product sizes/volumes: Available bottle sizes
   - Product disclaimer: Legal text with ABV information

## Technical Notes

1. **Age Verification**: The site has a JavaScript-based age verification gate, but this does not block direct HTML requests. Product pages are fully accessible via HTTP GET.

2. **Rendering**: The site uses Next.js with server-side rendering (SSR). All product data is present in the initial HTML response without requiring JavaScript execution.

3. **Images**: Product images are served from Contentful CDN (`images.ctfassets.net`) with automatic format optimization (supports AVIF, WebP).

4. **No Authentication**: Public product pages do not require authentication.

## Error Handling

All functions return structured responses with a `success` boolean:

```json
{
  "success": false,
  "error": "HTTP error: 404 Not Found",
  "url": "https://www.smirnoff.com/en-us/products/invalid-product"
}
```

Common errors:
- HTTP 404: Product not found
- HTTP 403: Access blocked (rare)
- Parse error: Unexpected page structure