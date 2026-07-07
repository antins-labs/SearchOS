# Beijing Government Map Service Access Skill

This skill fetches place/facility information from Beijing's official government map service (北京12345服务导图 - map.beijing.gov.cn).

## Overview

The Beijing Government Map Service is an official platform that provides comprehensive information about various public facilities across Beijing, including:
- Medical institutions (hospitals, clinics)
- Government service centers
- Educational facilities
- Transportation services
- Community services
- And many other public facilities

## Available Functions

### get_place

Fetch detailed information about a specific place using its placeId.

**Parameters:**
- `place_id` (required): The unique identifier for the place, e.g., "5bc7f4cf080b851f908bb5d1"
- `category_id` (optional): The category identifier, e.g., "sjyljg" for tertiary medical institutions

**Example:**
```python
result = await execute({
    'function': 'get_place',
    'place_id': '5bc7f4cf080b851f908bb5d1',
    'category_id': 'sjyljg'
})
```

### get_place_by_url

Fetch place information directly from a full URL.

**Parameters:**
- `url` (required): The complete URL of the place page

**Example:**
```python
result = await execute({
    'function': 'get_place_by_url',
    'url': 'https://map.beijing.gov.cn/map-web/place?placeId=5bc7f4cf080b851f908bb5d1&categoryId=sjyljg'
})
```

## Response Structure

```json
{
  "success": true,
  "place_name": "北京大学人民医院",
  "category": "三级医疗机构",
  "source_department": "市卫生健康委",
  "publish_date": "2018-10-18",
  "keywords": "北京大学人民医院",
  "address": "北京市西城区西直门南大街11号",
  "phone": "010-88325531",
  "zipcode": "100044",
  "place_id": "5bc7f4cf080b851f908bb5d1",
  "category_id": "sjyljg",
  "source_url": "https://map.beijing.gov.cn/map-web/place?placeId=5bc7f4cf080b851f908bb5d1&categoryId=sjyljg"
}
```

### Optional Fields

Depending on the place type, additional fields may be included:
- `office_hours`: Business hours (common for government offices)
- `services`: Related services (common for hospitals - appointment booking, WeChat services, apps)
- `data_source`: Source of the data
- `update_time`: Last update time

## Data Source

All information is extracted from the official Beijing Government website (map.beijing.gov.cn), which is operated by:
- Host: 北京市政务服务和数据管理局 (Beijing Municipal Government Services and Data Bureau)
- Data provided by various government departments

## Common Category IDs

Some known category IDs:
- `sjyljg`: 三级医疗机构 (Tertiary Medical Institutions)
- `xhnj`: 消化内镜检查医疗机构 (Digestive Endoscopy Medical Institutions)

## Limitations

- The website does not provide a public API, so data is extracted from HTML pages
- The skill currently only supports individual place detail pages
- Listing/search functionality for discovering places by category is not yet implemented

## Error Handling

The function returns a dict with `success: false` and an `error` field for failures:
```json
{
  "success": false,
  "error": "Place not found or unavailable"
}
```

Common errors:
- Invalid placeId format
- Place no longer available
- Network timeout
- Invalid URL format