# Johnnie Walker Product Catalog Access Skill

## Overview

This skill provides programmatic access to Johnnie Walker's whisky product catalog through their public search API. It allows you to search, browse, and retrieve detailed product information without dealing with the website's age gate or dynamic content loading.

## Capabilities

- **Search Products**: Search for specific Johnnie Walker whisky products by name or keywords
- **Browse All Products**: Retrieve the complete product catalog with detailed information
- **Filter by Category**: Get products from specific categories (core range, limited editions, gift boxes)
- **Product Details**: Access comprehensive product information including:
  - Product name and title
  - ABV and available bottle sizes
  - Product images and descriptions
  - Buy links to official store
  - Product features (engravable, gifts, etc.)
  - Product group/category

## Functions

### 1. search_products

Search for Johnnie Walker whisky products by name or keywords.

**Parameters:**
- `query` (string, optional): Search query for product name or type
- `limit` (integer, optional): Maximum number of results to return (default: 50)
- `locale` (string, optional): Locale for products (default: 'en-us')

**Example:**
```python
params = {
    'function': 'search_products',
    'query': 'black label',
    'limit': 10
}
result = await execute(params)
```

### 2. get_all_products

Retrieve all available Johnnie Walker whisky products.

**Parameters:**
- `limit` (integer, optional): Maximum number of results to return (default: 100)
- `locale` (string, optional): Locale for products (default: 'en-us')

**Example:**
```python
params = {
    'function': 'get_all_products',
    'limit': 50
}
result = await execute(params)
```

### 3. get_products_by_group

Get products filtered by product group/category.

**Parameters:**
- `group` (string, required): Product group/category
  - Valid values: 'core-range', 'limited-editions', 'gift-boxes'
- `limit` (integer, optional): Maximum number of results to return (default: 50)
- `locale` (string, optional): Locale for products (default: 'en-us')

**Example:**
```python
params = {
    'function': 'get_products_by_group',
    'group': 'limited-editions',
    'limit': 10
}
result = await execute(params)
```

## Return Value

All functions return a dictionary with the following structure:

```python
{
    'success': True,  # Boolean indicating success/failure
    'total_results': 29,  # Number of products returned
    'products': [...],  # List of product objects with full details
    'product_list': [  # Simplified list of products
        {
            'title': 'Johnnie Walker Black Label',
            'group': 'core-range',
            'url': 'https://www.johnniewalker.com/en-us/our-whisky/core-range/johnnie-walker-black-label',
            'buy_url': 'https://us.thebar.com/products/johnnie-walker-black-label/',
            'details': '40% ABV. Available in 50ml, 200ml, 375ml, 750ml, 1000ml, 1750ml',
            'features': ['whiskyGifts', 'engravable'],
            'sys_id': '6xb8ifuTTxgrSzUEAYaV2G'
        },
        ...
    ],
    'summary': '...',  # Human-readable formatted summary
    'function': 'search_products',  # Function that was executed
    'query': 'black',  # Original query (if applicable)
    'locale': 'en-us'  # Locale used
}
```

## Product Data Structure

Each product in the `products` array contains:

- `title`: Product name
- `listingTitle`: Display title for listings
- `group`: Product category ('core-range', 'limited-editions', 'gift-boxes')
- `url`: Product page URL path
- `detailBottleSize`: ABV and available bottle sizes
- `image`: Product image with multiple resolutions and formats
- `featuredImage`: Featured cocktail or lifestyle image
- `buyNowLink`: Direct purchase link
- `useMikMak`: Boolean indicating if MikMak shopping is enabled
- `buyNow`: Boolean indicating if direct purchase is available
- `productFeatures`: Array of product features (e.g., 'whiskyGifts', 'engravable')
- `productRange`: Product range classification
- `trending`: Trending score
- `pageViews`: Page view count
- `sysId`: Unique system identifier
- `locale`: Product locale
- `type`: Always 'product'

## Use Cases

1. **Product Discovery**: Browse the complete Johnnie Walker catalogue
2. **Price/Availability Check**: Get buy links for products
3. **Inventory Management**: Track product features and variants
4. **Content Creation**: Access high-quality product images and descriptions
5. **Market Research**: Analyze product range, features, and trends

## Technical Notes

- **API Endpoint**: `https://www.johnniewalker.com/api/search`
- **Method**: GET
- **Authentication**: None required (public API)
- **Rate Limiting**: Standard web rate limits apply
- **Response Format**: JSON

### API Parameters

- `indexName`: Index to search (e.g., 'index_products_prod_trending')
- `query`: Search query string
- `sortBy`: Sort order ('trending', 'az', 'za', 'age')
- `limit`: Maximum results
- `filters`: Contentful-style filters (e.g., "locale:'en-us'")
- `numericFilters`: Numeric filters (usually empty)

## Example Usage

```python
# Search for specific product
result = await execute({
    'function': 'search_products',
    'query': 'blue label',
    'limit': 5
})

# Get all products
result = await execute({
    'function': 'get_all_products'
})

# Get limited editions
result = await execute({
    'function': 'get_products_by_group',
    'group': 'limited-editions'
})

# Check results
if result['success']:
    for product in result['product_list']:
        print(f"{product['title']} - {product['details']}")
        print(f"  Buy: {product['buy_url']}")
else:
    print(f"Error: {result['error']}")
```

## Error Handling

The skill returns structured errors without raising exceptions:

```python
{
    'success': False,
    'error': 'Error description',
    'details': 'Additional details if available'
}
```

Common errors:
- Invalid function name
- Missing required parameters
- Network connectivity issues
- API rate limiting

## Notes

- The Johnnie Walker website has an age gate for human visitors, but the API is publicly accessible
- Product availability and pricing information comes from external retailer links (thebar.com)
- Images are hosted on Contentful CDN (images.ctfassets.net)
- The API uses Algolia-based search indices
- Product catalog includes ~29 products across 3 categories