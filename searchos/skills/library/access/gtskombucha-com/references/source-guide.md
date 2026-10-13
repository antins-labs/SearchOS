# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# GT's Living Foods E-commerce Catalog Access

This skill retrieves product and collection data from GT's Living Foods e-commerce website.

## Site Information

- **Primary Domain**: gtslivingfoods.com
- **Legacy Domain**: gtskombucha.com (redirects to gtslivingfoods.com)
- **Platform**: Shopify

## Available Functions

### list_collections

Lists all available product collections/categories.

**Example:**
```json
{
  "function": "list_collections"
}
```

**Returns:**
```json
{
  "success": true,
  "collections": [
    {
      "handle": "synergy-raw-kombucha",
      "url": "https://gtslivingfoods.com/collections/synergy-raw-kombucha",
      "title": "SYNERGY The Real Kombucha"
    }
  ],
  "count": 7
}
```

### get_collection

Retrieves products within a specific collection.

**Parameters:**
- `collection_handle` (required): The collection's URL handle
- `page` (optional): Page number for pagination (default: 1)

**Example:**
```json
{
  "function": "get_collection",
  "collection_handle": "synergy-raw-kombucha"
}
```

**Returns:**
```json
{
  "success": true,
  "collection": {
    "handle": "synergy-raw-kombucha",
    "title": "SYNERGY Raw Kombucha",
    "url": "https://gtslivingfoods.com/collections/synergy-raw-kombucha"
  },
  "products": [
    {
      "id": 4839153696821,
      "handle": "gts-kombucha-gingerade",
      "vendor": "GT's Living Foods",
      "type": "SYNERGY",
      "url": "https://gtslivingfoods.com/products/gts-kombucha-gingerade",
      "variants": [
        {
          "id": 32962758213685,
          "name": "Gingerade® - 16 Fl Oz x 6 Pack",
          "title": "16 Fl Oz x 6 Pack",
          "price": 48.0,
          "price_formatted": "$48.00",
          "sku": ""
        }
      ]
    }
  ],
  "count": 8,
  "page": 1,
  "has_next_page": false
}
```

### get_product

Retrieves detailed information about a single product.

**Parameters:**
- `product_handle` (required): The product's URL handle

**Example:**
```json
{
  "function": "get_product",
  "product_handle": "gts-kombucha-gingerade"
}
```

**Returns:**
```json
{
  "success": true,
  "product": {
    "id": 4839153696821,
    "handle": "gts-kombucha-gingerade",
    "vendor": "GT's Living Foods",
    "type": "SYNERGY",
    "name": "Gingerade®",
    "description": "Cold pressed ginger with a bold finish. Available in 16oz, 10oz, and 48oz.",
    "brand": "GT's Living Foods",
    "category": "SYNERGY",
    "image": "https://cdn.shopify.com/s/files/1/0287/2200/4021/files/SYN_FLAVORS_6.png",
    "url": "https://gtslivingfoods.com/products/gts-kombucha-gingerade",
    "variants": [
      {
        "id": 32962758213685,
        "name": "Gingerade® - 16 Fl Oz x 6 Pack",
        "title": "16 Fl Oz x 6 Pack",
        "price": 48.0,
        "price_formatted": "$48.00",
        "availability": "OutOfStock",
        "url": "https://gtslivingfoods.com/products/gts-kombucha-gingerade?variant=32962758213685"
      }
    ]
  }
}
```

### search_products

Searches for products matching a query.

**Parameters:**
- `query` (required): Search keywords

**Example:**
```json
{
  "function": "search_products",
  "query": "ginger"
}
```

## Known Collections

- `synergy-raw-kombucha` - SYNERGY Raw Kombucha products
- `classic-raw-kombucha` - Classic Raw Kombucha products
- `coconut-yogurt` - Coconut Yogurt products
- `agua-de-kefir-cultured-hydration` - Agua de Kefir products
- `alive-mood-mind` - Alive Mood & Mind products
- `aura-collagen-protein` - Aura Collagen Protein products
- `immortal-wellness-shots` - Immortal Wellness Shots

## Rate Limiting

The site has aggressive rate limiting. This skill implements a 3-second delay between requests to avoid HTTP 429 errors. When making multiple requests, be aware of this limitation.

## Data Source

Product and collection data is extracted from:
1. Embedded `var meta = {...}` JavaScript objects in HTML pages
2. JSON-LD structured data (Schema.org Product format)
3. Open Graph meta tags

All prices are returned in USD and converted from cents to dollars for readability.
