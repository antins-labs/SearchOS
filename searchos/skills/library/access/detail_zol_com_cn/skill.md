# ZOL Product Parameter Extractor

Extract product specifications and technical parameters from ZOL (中关村在线) product pages at detail.zol.com.cn.

## Overview

ZOL (ZOL.com.cn) is one of China's largest technology product databases. This skill extracts structured product specifications from their param pages, including:

- Basic parameters (发布时间, 上市日期, 使用场景, etc.)
- Physical specifications (外形: 长度, 宽度, 厚度, 重量)
- Hardware specs (硬件: CPU, GPU, RAM, ROM, 操作系统)
- Display specs (屏幕: 尺寸, 分辨率, 材质)
- Camera specs (摄像头)
- Network & connectivity (网络与连接)
- Battery info (电池与续航)
- Features & warranty info

## Functions

### get_params

Fetch complete product parameter information with structured category grouping.

**Parameters:**
- `url`: Full URL to the param.shtml page

**Example:**
```python
result = await execute({
    'function': 'get_params',
    'url': 'https://detail.zol.com.cn/1393/1392178/param.shtml'
})
```

**Returns:**
```json
{
  "success": true,
  "url": "https://detail.zol.com.cn/1393/1392178/param.shtml",
  "productId": "1392178",
  "productName": "Redmi Note 11（6GB/128GB/全网通/5G版）",
  "manufacturer": "红米",
  "category": "手机",
  "totalParams": 57,
  "categories": ["基本参数", "外形", "硬件", "屏幕", ...],
  "params": {
    "基本参数": [
      {"name": "国内发布时间", "value": "2021年10月28日"},
      {"name": "上市日期", "value": "2021年11月01日"}
    ],
    "硬件": [
      {"name": "CPU型号", "value": "联发科 天玑810"},
      {"name": "RAM容量", "value": "6GB"}
    ]
  }
}
```

### get_params_flat

Fetch parameters as a flat key-value dictionary with category-prefixed keys.

**Parameters:**
- `url`: Full URL to the param.shtml page

**Returns:**
```json
{
  "success": true,
  "params": {
    "基本参数.国内发布时间": "2021年10月28日",
    "基本参数.上市日期": "2021年11月01日",
    "硬件.CPU型号": "联发科 天玑810"
  }
}
```

### get_by_id

Fetch parameters using only the product ID (attempts to construct the URL).

**Parameters:**
- `product_id`: ZOL product ID (e.g., "1392178")

**Note:** This function tries common URL patterns and may not always work for all products.

### get_category

Fetch parameters for a specific category only.

**Parameters:**
- `url`: Full URL to the param.shtml page
- `category`: Category name or partial match (e.g., "硬件", "屏幕")

**Returns:**
```json
{
  "success": true,
  "category": "硬件",
  "params": [
    {"name": "CPU型号", "value": "联发科 天玑810"},
    {"name": "CPU频率", "value": "2.4Ghz A76*4+2.0GHz A55*4"}
  ]
}
```

## URL Format

ZOL param pages follow this URL pattern:
```
https://detail.zol.com.cn/{category_prefix}/{product_id}/param.shtml
```

For example:
- `https://detail.zol.com.cn/1393/1392178/param.shtml` (Redmi Note 11)
- `https://detail.zol.com.cn/1339/1338164/param.shtml` (Redmi Note 10)

## Supported Categories

Common parameter categories found on ZOL pages:
- 基本参数 (Basic parameters)
- 外形 (Physical dimensions)
- 硬件 (Hardware - CPU, RAM, ROM, etc.)
- 屏幕 (Display)
- 摄像头 (Camera)
- 网络与连接 (Network & connectivity)
- 电池与续航 (Battery)
- 功能与服务 (Features & services)
- 手机附件 (Phone accessories)
- 保修信息 (Warranty info)

## Implementation Notes

- Uses direct HTTP requests with GBK encoding support
- No browser automation required
- Parses HTML tables with BeautifulSoup
- Extracts metadata from embedded JavaScript `_PRO_` object
- Supports all product categories on ZOL (phones, laptops, tablets, etc.)

## Error Handling

Returns structured error responses:
```json
{
  "success": false,
  "error": "Failed to fetch page",
  "url": "..."
}
```

## Data Source

All data is fetched from detail.zol.com.cn, a product database site operated by ZOL (中关村在线), one of China's leading technology media and product database websites.