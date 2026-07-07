# Mi.com Product Spec Extractor

Extract detailed product specifications from Xiaomi's official website (mi.com).

## Overview

This skill accesses Xiaomi's official product pages to extract structured specification data. It supports both Hong Kong and Mainland China product pages.

### Key Features

- **Structured Spec Extraction**: Parses specification tables into organized sections
- **Multi-Region Support**: Works with both HK (`/hk/`) and Mainland China URLs
- **No JavaScript Required**: HK specs pages can be parsed directly with HTML parsing
- **Batch Processing**: Extract specs for multiple products in one call

## Supported URL Patterns

### Hong Kong Specs Pages (Recommended)
```
https://www.mi.com/hk/product/{product}/specs/
```
Example: `https://www.mi.com/hk/product/redmi-note-12-5g/specs/`

These URLs contain fully structured specification tables that can be parsed directly without JavaScript execution. This is the most reliable method.

### Hong Kong Product Pages
```
https://www.mi.com/hk/product/{product}/
```
Example: `https://www.mi.com/hk/product/redmi-note-12-5g/`

Basic product info available; for full specs, use the `/specs/` URL.

### Mainland China Product Pages
```
https://www.mi.com/{product}
https://www.mi.com/prod/{product}
```
Examples:
- `https://www.mi.com/redmi-note-13-5g`
- `https://www.mi.com/prod/redmi-note-14`

These pages are Vue.js applications and require Playwright for full spec extraction.

## Usage

### Basic Usage

```python
from executor import execute

# Extract specs from a Hong Kong specs page
result = await execute({
    'url': 'https://www.mi.com/hk/product/redmi-note-12-5g/specs/'
})

print(result['product']['name'])  # "Redmi Note 12 5G"
print(result['product']['specs'].keys())  # ['螢幕', '設計', '後置鏡頭', ...]
```

### Extracting Multiple Products

```python
result = await execute({
    'urls': [
        'https://www.mi.com/hk/product/redmi-note-12-5g/specs/',
        'https://www.mi.com/hk/product/redmi-note-13-5g/specs/',
    ]
})

for product in result['products']:
    print(f"{product['name']}: {len(product['specs'])} sections")
```

### Using Playwright for Mainland China Pages

```python
result = await execute({
    'url': 'https://www.mi.com/redmi-note-13-5g',
    'use_playwright': True
})
```

## Output Structure

```json
{
  "success": true,
  "product": {
    "name": "Redmi Note 12 5G",
    "url": "https://www.mi.com/hk/product/redmi-note-12-5g/specs/",
    "title": "Redmi Note 12 5G 規格與功能 | Xiaomi 香港",
    "description": "Redmi Note 12 5G 規格...",
    "image": "//i02.appmifile.com/.../product.png",
    "region": "Hong Kong",
    "specs": {
      "螢幕": [
        {"text": "6.67\" AMOLED DotDisplay 螢幕", "data_key": "spec_3"},
        {"text": "螢幕更新頻率：高達 120Hz", "data_key": "spec_5"},
        {"text": "450 尼特（典型值），HBM 700 尼特，1200 尼特峰值亮度", "data_key": "spec_7"}
      ],
      "設計": [
        {"text": "165.88*76.21*7.98mm", "data_key": "spec_16"},
        {"text": "189g", "data_key": "spec_17"},
        {"text": "瑪瑙灰、森林綠、冰河藍", "data_key": "spec_18"}
      ],
      "後置鏡頭": [
        {"text": "4800 萬像素主鏡頭", "data_key": "spec_20"},
        {"text": "f/1.8", "data_key": "spec_23"},
        ...
      ],
      ...
    },
    "raw_specs": [
      {"section": "螢幕", "text": "6.67\" AMOLED DotDisplay 螢幕", "data_key": "spec_3"},
      ...
    ]
  }
}
```

## Spec Sections

Hong Kong specs pages typically include the following sections (in Traditional Chinese):

| English | Chinese | Description |
|---------|---------|-------------|
| Display | 螢幕 | Screen specifications |
| Design | 設計 | Physical dimensions and colors |
| Rear Camera | 後置鏡頭 | Main camera specifications |
| Front Camera | 前置自拍鏡頭 | Selfie camera specifications |
| Chip | 晶片 | Processor and GPU |
| Memory | 記憶體 | RAM and storage |
| Battery | 電池 | Battery capacity |
| Charging | 充電 | Charging specifications |
| Cooling | 散熱系統 | Cooling system |
| Security | 安全和認證 | Security features |
| Connectivity | 連接 | Network and connectivity |
| Vibration Motor | 震動馬達 | Haptic feedback |
| Water Resistance | 防水防塵 | IP rating |
| NFC | NFC | NFC support |
| Navigation | 導航 | GPS and positioning |
| Audio | 音訊 | Audio features |
| Sensors | 感應器 | Various sensors |
| OS | 用戶介面和系統 | Operating system |
| Package Contents | 包裝內容 | What's in the box |

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | string | - | Single product URL |
| `urls` | array | - | List of product URLs |
| `use_playwright` | boolean | false | Force Playwright rendering |
| `include_raw_specs` | boolean | true | Include flat raw_specs array |

## Technical Details

### Parsing Method

1. **Hong Kong Specs Pages**: Direct HTML parsing using BeautifulSoup
   - Identifies spec sections by font-size styling (headers use 35px font)
   - Extracts spec items from `<span class="xm-text">` elements
   - Each item has a `data-key` attribute for cross-referencing

2. **Mainland China Pages**: Playwright browser rendering
   - Waits for Vue.js app to fully render
   - Extracts data from DOM after JavaScript execution
   - Parses tables, definition lists, and spec items

### Data Key System

Each spec item has a `data-key` attribute like `spec_3`, `spec_5`, etc. This can be used to:
- Cross-reference specs between different language versions
- Track which spec is which when product information is updated

## Dependencies

Required:
- `aiohttp` - HTTP client for async requests
- `beautifulsoup4` - HTML parsing

Optional:
- `playwright` - For Mainland China pages (install with: `pip install playwright && playwright install chromium`)

## Examples

### Get display specifications

```python
result = await execute({'url': 'https://www.mi.com/hk/product/redmi-note-12-5g/specs/'})

display_specs = result['product']['specs'].get('螢幕', [])
for spec in display_specs:
    print(f"- {spec['text']}")
```

Output:
```
- 6.67" AMOLED DotDisplay 螢幕
- 螢幕更新頻率：高達 120Hz
- 450 尼特（典型值），HBM 700 尼特，1200 尼特峰值亮度
- 對比度：4500000:1
- DCI-P3 寬廣色域
- 解析度：2400 x 1080
- 陽光螢幕
- 閱讀模式
```

### Search for specific spec

```python
result = await execute({
    'url': 'https://www.mi.com/hk/product/redmi-note-12-5g/specs/',
    'include_raw_specs': True
})

# Find battery capacity
for spec in result['product']['raw_specs']:
    if '電池' in spec['section'] or 'Battery' in spec['section']:
        print(f"{spec['section']}: {spec['text']}")
```

## Limitations

1. Mainland China pages require Playwright and are slower to process
2. Spec section names are in Chinese and may vary by region
3. Some specs may be listed under different sections for different products
4. The parser relies on HTML structure which may change if Xiaomi updates their site

## Error Handling

```python
result = await execute({'url': 'https://www.mi.com/hk/product/invalid-product/specs/'})

if not result['success']:
    print(f"Error: {result.get('error')}")
```