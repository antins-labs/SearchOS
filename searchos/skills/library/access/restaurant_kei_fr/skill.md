# Restaurant KEI (Paris) Access Skill

This skill provides programmatic access to Restaurant KEI's information and product catalog.

## About Restaurant KEI

Restaurant KEI is a Michelin-starred restaurant in Paris, France, led by Chef Kei Kobayashi.
- **Location**: 5 Rue Coq Héron, 75001 Paris, France
- **Website**: https://restaurant-kei.fr
- **Shopify Store**: The site uses Shopify for gift card and product sales

## Available Functions

### `fetch_home_page`
Fetches restaurant information from the home page, including:
- Address and location
- Contact information
- Opening hours
- Important notes (dress code, policies, etc.)

**Parameters:**
- `lang`: Language code (`'en'` for English, `'fr'` for French)

**Example:**
```python
result = await execute({
    'function': 'fetch_home_page',
    'lang': 'en'
})
```

### `get_contact_info`
Returns structured contact information for the restaurant.

**Example:**
```python
result = await execute({
    'function': 'get_contact_info'
})
```

Returns:
- Restaurant name and chef
- Street address, city, country
- Phone number
- Reservation email
- Website URL
- Opening hours (if available)
- Booking notes

### `list_products`
Lists all products available in the Shopify store, including:
- Gift cards (Carte Cadeau)
- Gift sets (Coffret Prestige, Coffret Horizon)
- Books (signed copies)
- Other items

**Parameters:**
- `limit`: Maximum products to return (default: 50, max: 250)
- `product_type`: Filter by product type (e.g., `'Carte Cadeau'`, `'Livre'`)

**Example:**
```python
result = await execute({
    'function': 'list_products',
    'product_type': 'Carte Cadeau'
})
```

### `get_product`
Get detailed information about a specific product.

**Parameters:**
- `handle`: Product handle/slug (e.g., `'bon-cadeau-kei-kobayashi'`)
- `product_id`: Shopify product GID (alternative to handle)

**Example:**
```python
result = await execute({
    'function': 'get_product',
    'handle': 'livre-dedicace-kei-iii'
})
```

### `list_collections`
List all product collections/categories.

**Parameters:**
- `limit`: Maximum collections to return (default: 20, max: 250)

**Example:**
```python
result = await execute({
    'function': 'list_collections'
})
```

Collections include:
- Gift cards (Les cartes cadeaux)
- Wine pairings (Cartes cadeaux menu accord mets et vins)
- Books (Livre)
- Pantry items (L'épicerie)

### `get_collection`
Get detailed information about a specific collection including all its products.

**Parameters:**
- `handle`: Collection handle/slug
- `limit`: Maximum products to return (default: 50)

**Example:**
```python
result = await execute({
    'function': 'get_collection',
    'handle': 'les-cartes-cadeaux'
})
```

## Response Format

All functions return a dictionary with:
- `success`: Boolean indicating if the operation succeeded
- On success: function-specific data (e.g., `products`, `restaurant`, `contact`)
- On failure: `error` key with error message

## Notes

- Menu items themselves are not available via API; only gift cards, books, and other shop items
- The restaurant uses a reservation management system not exposed via this API
- Price information is returned in EUR (€)
- For reservations, contact the restaurant directly via phone or email

## Data Sources

- Restaurant information: Scraped from https://restaurant-kei.fr
- Products and collections: Shopify Storefront API
- API Access Token: Public storefront token embedded in the website