# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Instant Gaming Product Page Access Skill

This skill retrieves detailed product information from Instant Gaming product pages.

## Supported Functions

### get_product_info

Fetches comprehensive product data from an Instant Gaming product page URL.

**Parameters:**
- `url` (required): The full Instant Gaming product page URL

**Returns:**
- `success`: Boolean indicating if the request was successful
- `title`: Full product title (from Open Graph meta tag)
- `display_title`: Display title shown on the page
- `url`: Canonical product URL
- `image`: Product cover image URL
- `description`: Product description
- `current_price`: Current sale price (e.g., "$5.46")
- `original_price`: Original retail price (e.g., "$9")
- `discount_percent`: Discount percentage (e.g., -39)
- `price_numeric`: Numeric price value for calculations
- `original_price_numeric`: Numeric original price value
- `currency`: Price currency (e.g., "USD")
- `in_stock`: Boolean indicating if product is in stock
- `stock_text`: Stock status text (e.g., "In stock")
- `platform`: Platform name (e.g., "Steam")
- `platform_icon`: Platform icon CSS class
- `sku`: Product SKU/ID number
- `category`: Product category path
- `publisher`: Publisher name
- `availability`: Schema.org availability URL
- `digital_download`: Boolean indicating if it's a digital download
- `regions`: List of available regions with their prices
  - `name`: Region name (e.g., "Europe")
  - `value`: Region product ID
  - `price`: Price for that region
  - `href`: URL for that region's product page

## Example Usage

```json
{
  "function": "get_product_info",
  "url": "https://www.instant-gaming.com/en/16754-buy-total-war-warhammer-iii-tamurkhan-thrones-of-decay-pc"
}
```

## Example Response

```json
{
  "success": true,
  "title": "Buy Total War: Warhammer III - Tamurkhan – Thrones of Decay - PC (Steam) - Europe",
  "display_title": "Total War: Warhammer III - Tamurkhan – Thrones of Decay - PC (Steam)",
  "url": "https://www.instant-gaming.com/en/16754-buy-total-war-warhammer-iii-tamurkhan-thrones-of-decay-pc-game-steam-europe/",
  "image": "https://gaming-cdn.com/images/products/16754/orig-fallback-v1/total-war-warhammer-iii-tamurkhan-thrones-of-decay-pc-game-steam-europe-cover.jpg",
  "current_price": "$5.46",
  "original_price": "$9",
  "discount_percent": -39,
  "price_numeric": 5.46,
  "original_price_numeric": 9.0,
  "currency": "USD",
  "in_stock": true,
  "stock_text": "In stock",
  "platform": "Steam",
  "sku": "16754",
  "category": "Software > Video Game Software > Computer Games",
  "publisher": "Feral Interactive",
  "regions": [
    {
      "name": "Europe",
      "value": "16754",
      "price": "$5.46",
      "href": "https://www.instant-gaming.com/en/16754-buy-total-war-warhammer-iii-tamurkhan-thrones-of-decay-pc-game-steam-europe/"
    },
    {
      "name": "Latin America",
      "value": "16755",
      "price": "$9.11",
      "href": "https://www.instant-gaming.com/en/16755-buy-total-war-warhammer-iii-tamurkhan-thrones-of-decay-pc-mac-game-steam-latin-america/"
    }
  ]
}
```

## Notes

- Uses Playwright browser automation to handle JavaScript-rendered content
- Prices are displayed in the user's regional currency (typically USD)
- Region options show different prices for different geographical regions
- The skill validates that URLs are from www.instant-gaming.com domain
- All prices include numeric versions for easy calculation
