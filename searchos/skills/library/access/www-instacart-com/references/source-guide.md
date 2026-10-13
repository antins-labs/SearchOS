# 来源操作说明

此文保留原有查询语义、分页和来源限制。调用以 SKILL.md 中的独立 CLI 为准；旧函数示例对应 --params 的 JSON 参数。

# Instacart Product Page Access Skill

This skill fetches detailed product information from Instacart's cross-retailer product detail pages.

## Features

Extracts comprehensive product data including:
- **Basic Info**: Product name, brand, size, category
- **Descriptions**: Product description and marketing details
- **Ingredients**: Full ingredient list (when available)
- **Nutrition**: Calorie information and nutritional details
- **Pricing**: Starting price (when available)
- **Images**: Product image URLs
- **Navigation**: Breadcrumb category path

## Usage

### Get Product by URL

```python
result = await execute({
    "function": "get_product",
    "url": "https://www.instacart.com/products/20248583-rowdy-mermaid-rowdy-belly-12-fl-oz"
}, ctx)
```

### Get Product by ID

```python
result = await execute({
    "function": "get_product",
    "product_id": "20248583"
}, ctx)
```

## Response Structure

```json
{
  "success": true,
  "product_id": "20248583",
  "name": "Rowdy Mermaid Kombucha, Rowdy Belly",
  "brand": "Rowdy Mermaid",
  "size": "12 fl oz",
  "category": "Kombucha",
  "starting_price": 3.79,
  "description": "Rowdy Mermaid Rowdy Belly Kombucha 12 fl oz",
  "details": "Designed for digestion. Contains live culture...",
  "ingredients": "BREWED TEA (FILTERED WATER, GREEN TEA*, BLACK TEA*), CANE SUGAR*...",
  "ingredients_list": ["BREWED TEA (FILTERED WATER, GREEN TEA*, BLACK TEA*)", "CANE SUGAR*", ...],
  "directions": "Keep me in the fridge.",
  "calories": 45,
  "has_nutritional_info": true,
  "gluten_free": true,
  "images": ["https://www.instacart.com/image-server/..."],
  "breadcrumbs": [
    {"name": "Beverages", "url": "https://www.instacart.com/categories/243-beverages"},
    {"name": "Kombucha", "url": "https://www.instacart.com/categories/243-beverages/278-kombucha"}
  ],
  "source_url": "https://www.instacart.com/store/products/20248583?x_retailer=true"
}
```

## Notes

- The skill uses Instacart's cross-retailer product detail pages (`/store/products/{id}?x_retailer=true`)
- Data is extracted from embedded JSON payloads in the HTML response
- Some products may have limited data availability (e.g., missing ingredients or nutrition info)
- The `starting_price` is a fallback price and may not reflect actual prices in your area
- Product availability and data may vary by region

## Limitations

- Requires the product to be available on Instacart's cross-retailer platform
- Some products may redirect to the homepage if not found
- Nutrition and ingredient data availability varies by product
- The skill fetches static product data; real-time pricing requires location context
