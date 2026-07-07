# Luzhou Laojiao Brand Products Access Skill

Access brand and product information from Luzhou Laojiao (泸州老窖) official website.

## Site Overview

- **Host**: `www.lzlj.com`
- **Type**: Static HTML (server-side rendered)
- **Content**: Chinese liquor/white spirit brand information and products

## Available Functions

### 1. `list_brands`

List all available brand categories from Luzhou Laojiao.

**Parameters**: None

**Returns**:
```json
{
  "brands": [
    {
      "name": "国窖1573",
      "slug": "1573",
      "url": "http://www.lzlj.com/brand/1573/"
    }
  ],
  "count": 11
}
```

### 2. `list_products`

List all products under a specific brand category.

**Parameters**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| brand_slug | string | Yes | Brand slug (e.g., '1573', 'tequ', '1952') |

**Returns**:
```json
{
  "brand_slug": "1573",
  "brand_intro": "国窖1573源自全国重点文物保护单位...",
  "products": [
    {
      "id": "3742",
      "name": "国窖1573经典装",
      "url": "http://www.lzlj.com/brand/1573/3742.html",
      "image": "http://www.lzlj.com/upload/image/..."
    }
  ],
  "count": 13
}
```

### 3. `get_product_detail`

Get detailed information about a specific product.

**Parameters**:
| Name | Type | Required | Description |
|------|------|----------|-------------|
| product_url | string | Yes | Full URL or path to product page |

**Returns**:
```json
{
  "url": "http://www.lzlj.com/brand/1573/3742.html",
  "name": "国窖1573经典装",
  "introduction": "国窖1573经典装源自全国重点文物保护单位...",
  "specifications": {
    "度数": "38%vol43%vol46%vol52%vol",
    "规格": "50ml100ml250ml375ml500ml750ml1.5L3L"
  },
  "images": ["http://www.lzlj.com/upload/image/..."],
  "meta_description": "泸州老窖"
}
```

## Brand Slugs Reference

| Brand Name | Slug |
|------------|------|
| 国窖1573 | 1573 |
| 1952 | 1952 |
| 特曲 | tequ |
| 窖龄酒 | jiaolingjiu |
| 高光 | gaoguang |
| 头曲 | touqu |
| 黑盖 | heigai |
| 二曲 | erqu |
| 养生酒 | yangshengjiu |
| 新酒业 | xinjiuye |
| 定制酒 | dingzhijiu |

## Usage Examples

### List all brands
```python
result = await execute({
    "function": "list_brands"
})
```

### List products in a brand
```python
result = await execute({
    "function": "list_products",
    "brand_slug": "1573"
})
```

### Get product details
```python
result = await execute({
    "function": "get_product_detail",
    "product_url": "http://www.lzlj.com/brand/1573/3742.html"
})

# Or with relative path
result = await execute({
    "function": "get_product_detail",
    "product_url": "/brand/1573/3742.html"
})
```

## Technical Notes

1. **Site Structure**: The site uses server-side rendered HTML with no XHR/API calls. All data is extracted from the HTML content.

2. **URL Patterns**:
   - Brand listing: `/brand/`
   - Brand products: `/brand/{brand_slug}/`
   - Product detail: `/brand/{brand_slug}/{product_id}.html`

3. **Product Images**: All images use the `/upload/image/` path prefix. The skill converts relative URLs to absolute URLs.

4. **Specifications**: Product specifications (度数/alcohol content, 规格/size) are extracted from the `specs-item` CSS class elements.

5. **Character Encoding**: The site uses UTF-8 encoding. Chinese text is properly preserved.

## Error Handling

All functions return a dictionary with an `error` key if something goes wrong:

```json
{
  "error": "Failed to fetch product page: http://example.com/invalid"
}
```