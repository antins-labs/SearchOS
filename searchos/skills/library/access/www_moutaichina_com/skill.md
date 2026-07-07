# Moutai China Product Catalog Access Skill

Access product information from Moutai China's official website (www.moutaichina.com).

## Overview

This skill provides access to Moutai China's product catalog, including:
- Product listings by category
- Detailed product specifications
- Product categories and series
- Search functionality

## Available Functions

### 1. `list_products`

List products from a specific category with pagination.

**Parameters:**
- `category` (string): Product category
  - `"all"` - All products (default)
  - `"moutai_series"` - 贵州茅台酒 (Guizhou Moutai Liquor series)
  - `"jiangxiang_series"` - 酱香系列酒 (Jiangxiang series liquor)
- `page` (integer): Page number (default: 1)

**Example:**
```python
result = await execute({
    "function": "list_products",
    "category": "moutai_series",
    "page": 1
})
```

**Returns:**
```json
{
  "success": true,
  "products": [
    {
      "name": "贵州茅台酒（飞天）",
      "url": "https://www.moutaichina.com/mtgf/2023-10/31/article_2023103117423682414.html",
      "id": "article_2023103117423682414",
      "image": "https://www.moutaichina.com/mtgf/imageDir/...",
      "specs": {
        "香型": "酱香型白酒",
        "酒精含量": "53%vol",
        "规格": "500ml/瓶"
      }
    }
  ],
  "pagination": {
    "current_page": 1,
    "total_pages": 2,
    "total_items": 13
  }
}
```

### 2. `get_product`

Get detailed product information from a product URL.

**Parameters:**
- `url` (string, required): Product detail page URL

**Example:**
```python
result = await execute({
    "function": "get_product",
    "url": "https://www.moutaichina.com/mtgf/2023-10/31/article_2023103117423682414.html"
})
```

**Returns:**
```json
{
  "success": true,
  "product": {
    "name": "贵州茅台酒（飞天）",
    "url": "https://www.moutaichina.com/mtgf/...",
    "image": "https://www.moutaichina.com/mtgf/...",
    "specs": {
      "香型": "酱香型白酒",
      "酒精含量": "53%vol",
      "规格": "500ml/瓶",
      "彩盒尺寸": "235*88*88mm",
      "配料": "高粱、小麦、水",
      "储存条件": "阴凉、干燥、密封保存，开启后请尽快饮用"
    },
    "fragrance_type": "酱香型白酒",
    "alcohol_content": "53%vol",
    "volume": "500ml/瓶"
  }
}
```

### 3. `get_categories`

Get all available product categories and series.

**Example:**
```python
result = await execute({
    "function": "get_categories"
})
```

**Returns:**
```json
{
  "success": true,
  "categories": [
    {
      "name": "全部展示",
      "url": "https://www.moutaichina.com/mtgf/cpzx/index.html",
      "is_active": true
    },
    {
      "name": "贵州茅台酒",
      "url": "https://www.moutaichina.com/mtgf/cpzx/mtjxl/index.html"
    },
    {
      "name": "酱香系列酒",
      "url": "https://www.moutaichina.com/mtgf/cpzx/jxxlj62/index.html"
    },
    {
      "series": "陈年贵州茅台酒系列：",
      "products": ["陈年贵州茅台酒（80）", "陈年贵州茅台酒（50）", ...]
    }
  ]
}
```

### 4. `search`

Search products by name (client-side filtering).

**Parameters:**
- `query` (string, required): Search query
- `category` (string, optional): Category to search within (default: "all")

**Example:**
```python
result = await execute({
    "function": "search",
    "query": "飞天",
    "category": "moutai_series"
})
```

## Product Categories

The site organizes products into these main categories:

1. **贵州茅台酒 (moutai_series)**: Premium Moutai liquor series
   - 陈年贵州茅台酒（80/50/30/15）
   - 贵州茅台酒（飞天）
   - 贵州茅台酒（五星）
   - 贵州茅台酒（珍品）
   - 贵州茅台酒（精品）
   - 贵州茅台酒（笙乐飞天）
   - 飞天系列生肖酒
   - 低度系列

2. **酱香系列酒 (jiangxiang_series)**: Jiangxiang series liquor
   - 茅台1935
   - 茅台迎宾酒
   - 贵州大曲
   - 王子酒系列

## Technical Notes

- **No API required**: The site serves static HTML content
- **Direct HTTP requests**: Uses aiohttp for efficient fetching
- **Pagination**: Automatically handles multi-page listings
- **Chinese content**: All product names and specifications are in Chinese

## Error Handling

All functions return structured error responses:
```json
{
  "success": false,
  "error": "Error description"
}
```

Common errors:
- Invalid category specified
- Missing required parameters
- Failed to fetch page
- Product not found