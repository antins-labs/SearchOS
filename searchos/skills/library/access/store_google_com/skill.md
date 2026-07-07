# Google Store Product Specs Access Skill

This skill retrieves detailed product specifications from the Google Store (store.google.com), supporting Pixel phones, tablets, and audio devices.

## Features

- **Get Product Specs**: Retrieve comprehensive technical specifications for any Google hardware product
- **List Products**: View all known available product spec pages
- **Search Products**: Find products by name or type

## Supported Products

Current known valid product spec pages include:

| Product Slug | Product Name |
|--------------|--------------|
| `pixel_10_pro_specs` | Pixel 10 Pro / Pro XL |
| `pixel_10_pro_fold_specs` | Pixel 10 Pro Fold |
| `pixel_9a_specs` | Pixel 9a |
| `pixel_9_specs` | Pixel 9 |
| `pixel_9_pro_specs` | Pixel 9 Pro / Pro XL |
| `pixel_tablet_specs` | Pixel Tablet |
| `pixel_buds_pro_2_specs` | Pixel Buds Pro 2 |

**Note**: Product availability changes frequently. Older products (Pixel 8, 7, 6 series) are often discontinued and may redirect to category pages or refurbished product listings.

## Usage Examples

### Get Product Specifications

```python
params = {
    "function": "get_specs",
    "product_slug": "pixel_9a_specs"
}
```

Returns detailed specs organized by category:
- Display specifications
- Dimensions and weight
- Battery and charging
- Memory and storage
- Processor details
- Camera specifications (front and rear)
- Video capabilities
- Connectivity options
- And more...

### List Available Products

```python
params = {
    "function": "list_products"
}
```

Returns a list of known valid product spec pages.

### Search for Products

```python
params = {
    "function": "search_products",
    "query": "pixel 9"
}
```

Returns products matching the search query.

## Output Structure

For `get_specs`, the output includes:

```json
{
  "product_slug": "pixel_9a_specs",
  "title": "Explore Pixel 9a Phone Specifications - Google Store",
  "url": "https://store.google.com/product/pixel_9a_specs?hl=en-US",
  "product_name": "Pixel 9a",
  "price": "$499",
  "specifications": {
    "Colors": ["Obsidian", "Porcelain", "Iris", "Peony"],
    "Display": [
      "6.3-inch Actua display",
      "20:9 aspect ratio",
      "1080 x 2424 pOLED at 422.2 PPI",
      ...
    ],
    "Battery and charging": [...],
    "Rear camera": [...],
    ...
  },
  "raw_text": "Full page text content..."
}
```

## Error Handling

The skill handles several error cases:

- **Product discontinued**: When a product slug redirects to a category page
- **Timeout**: When the page fails to load within the timeout period
- **Invalid product**: When the product slug doesn't match any known product

## Implementation Notes

- Uses Playwright to render JavaScript-heavy pages
- Extracts structured specifications from rendered text content
- Handles page redirects gracefully
- Includes raw text for flexibility in parsing
- Supports both current and legacy product URLs

## Limitations

- Google Store frequently updates available products; older generation devices may not be accessible
- Some products redirect to refurbished listings or category pages
- The skill relies on the page structure and may need updates if Google Store changes their layout