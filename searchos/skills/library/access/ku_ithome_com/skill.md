# IT Home Product Encyclopedia Access Skill

## Overview

This skill extracts device specifications and parameters from IT Home's product encyclopedia (IT之家产品百科) at ku.ithome.com. It specializes in structured data extraction from product specification pages, recovering detailed parameter tables that generic readers often miss.

## Target Site

- **Host**: ku.ithome.com
- **Type**: Consumer electronics product database
- **Content**: Specifications for phones, tablets, laptops, and other electronics
- **Language**: Chinese (Simplified)

## Why Use This Skill

The generic reader may miss structured parameter data (evidence showed 28 vs 0 parameters extracted). This skill:
- Properly parses HTML tables with structured specifications
- Extracts section groupings (基本情報, 硬件, 摄像头, etc.)
- Handles Chinese text encoding correctly
- Provides complete parameter key-value pairs

## Functions

### get_item_specs

Extract complete specification tables from a product's canshu (parameters) page.

**Parameters:**
- `item_id` (string): Product ID, e.g., "11168" for Redmi K20
- `url` (string): Full URL (alternative to item_id)
- `sections` (array): Optional filter for specific sections, e.g., ["硬件", "摄像头"]

**Example:**
```python
result = await execute({
    'function': 'get_item_specs',
    'item_id': '11168'
})
```

**Returns:**
```json
{
  "success": true,
  "item_id": "11168",
  "product": {
    "name": "Redmi K20(8GB/256GB/全网通)",
    "brand": "Redmi手机",
    "category": "手机"
  },
  "specifications": [
    {
      "name": "基本信息",
      "parameters": [
        {"name": "发布日期（北京时间）", "value": "2019-05-27"},
        {"name": "上市日期（北京时间）", "value": "2019-05-27"},
        {"name": "出厂系统版本", "value": "MIUI 10"},
        {"name": "出厂系统内核", "value": "Android 9.0"}
      ]
    },
    {
      "name": "硬件",
      "parameters": [
        {"name": "CPU品牌", "value": "高通"},
        {"name": "CPU型号", "value": "高通骁龙730"},
        {"name": "CPU核心数", "value": "八核"},
        {"name": "RAM容量", "value": "8GB"},
        {"name": "ROM容量", "value": "256GB"},
        {"name": "电池容量（典型值）", "value": "4000mAh"}
      ]
    }
  ],
  "summary": {
    "total_sections": 7,
    "total_parameters": 38,
    "section_names": ["基本信息", "硬件", "摄像头", "外观", "网络与连接", "功能与服务", "保修信息"]
  }
}
```

### get_item_overview

Get summary overview for a product including description and available pages.

**Parameters:**
- `item_id` (string): Product ID
- `url` (string): Full URL (alternative to item_id)

**Example:**
```python
result = await execute({
    'function': 'get_item_overview',
    'item_id': '11168'
})
```

### search_items

Browse items by category. Limited functionality - provides category listing only.

**Parameters:**
- `category` (string): Category name (default: "手机")
  - "手机" or "phone" - Mobile phones
  - "平板" or "tablet" - Tablets  
  - "笔记本" or "laptop" - Laptops
- `page` (integer): Page number (default: 1)

**Example:**
```python
result = await execute({
    'function': 'search_items',
    'category': '手机',
    'page': 1
})
```

## Common Specification Sections

The site organizes parameters into these typical sections:

| Section (Chinese) | Section (English) | Typical Parameters |
|-------------------|-------------------|-------------------|
| 基本信息 | Basic Info | Release date, OS version |
| 硬件 | Hardware | CPU, GPU, RAM, ROM, Battery |
| 摄像头 | Camera | Camera count, flash, features |
| 外观 | Appearance | Dimensions, weight, design |
| 网络与连接 | Network & Connectivity | SIM, NFC, bands, Bluetooth |
| 功能与服务 | Features & Services | Special features, audio |
| 保修信息 | Warranty | Warranty policy, support |

## URL Patterns

The site uses predictable URL patterns:

- **Overview**: `https://ku.ithome.com/item/{item_id}.html`
- **Specification**: `https://ku.ithome.com/item/{item_id}/canshu.html`
- **Images**: `https://ku.ithome.com/item/{item_id}/tupian.html`
- **Reviews**: `https://ku.ithome.com/item/{item_id}/pingce.html`
- **Category search**: `https://ku.ithome.com/search/c{cat_id}_s1_p{page}.html`

## Known Item IDs

For testing:
- **11168**: Redmi K20 (8GB/256GB/全网通)
- **11271**: Redmi Note 7系列
- **35219**: iPhone 14 Pro Max

## Error Handling

The executor returns structured error objects instead of raising exceptions:

```json
{
  "error": "HTTP error: 404",
  "error_code": "HTTP_ERROR",
  "status_code": 404
}
```

Error codes:
- `MISSING_FUNCTION`: No function specified
- `UNKNOWN_FUNCTION`: Invalid function name
- `MISSING_IDENTIFIER`: Neither item_id nor url provided
- `HTTP_ERROR`: HTTP request failed
- `TIMEOUT`: Request timed out
- `EXTRACTION_ERROR`: Parsing failed

## Technical Details

- **Method**: HTTP GET + HTML parsing (BeautifulSoup)
- **No API available**: Site renders server-side, no JSON APIs found
- **Rate limiting**: 2 requests/second recommended
- **Encoding**: UTF-8, Chinese text supported
- **Timeout**: 30 seconds default

## Limitations

1. **No search API**: Full-text search not available; only category browsing
2. **Brand filtering**: Brand ID mapping not implemented
3. **Reviews/Images**: Only spec extraction is fully supported
4. **Dynamic content**: Some linked helper pages not extracted