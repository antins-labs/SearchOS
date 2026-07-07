# 泸州老窖国际发展（香港）有限公司产品目录访问技能

## 概述

本技能用于从 www.lzljglobal.com 网站获取泸州老窖产品目录数据，包括产品列表、产品详情、分类信息和搜索功能。

## 网站

- 主站：https://www.lzljglobal.com
- 类型：静态HTML产品目录网站
- 语言：中文

## 功能说明

### 1. 获取分类列表 (get_categories)

获取所有可用的产品分类。

**参数：** 无需额外参数

**示例：**
```python
result = await execute({
    "function": "get_categories"
})
```

**返回示例：**
```json
{
    "success": true,
    "categories": [
        {
            "category_id": "15",
            "name": "国窖1573",
            "url": "https://www.lzljglobal.com/col15/list"
        },
        {
            "category_id": "16",
            "name": "泸州老窖头曲",
            "url": "https://www.lzljglobal.com/col16/list"
        },
        ...
    ]
}
```

### 2. 获取产品列表 (list_products)

获取指定分类的产品列表，支持分页。

**参数：**
- `category_id` (必需): 分类ID
- `page` (可选): 页码，默认为1

**示例：**
```python
# 获取国窖1573产品列表
result = await execute({
    "function": "list_products",
    "category_id": "15"
})

# 获取第2页产品
result = await execute({
    "function": "list_products",
    "category_id": "18",
    "page": 2
})
```

**返回示例：**
```json
{
    "success": true,
    "category_id": "15",
    "category_name": "国窖1573",
    "page": 1,
    "products": [
        {
            "product_id": "11",
            "title": "国窖1573·澳网纪念版",
            "url": "https://www.lzljglobal.com/col15/11",
            "image": "https://www.lzljglobal.com/upload/image/2025-10/col15/1761546960466.png",
            "category_id": "15"
        },
        ...
    ],
    "count": 3
}
```

### 3. 获取产品详情 (get_product)

获取单个产品的详细信息。

**参数：**
- `category_id` (必需): 分类ID
- `product_id` (必需): 产品ID

**示例：**
```python
result = await execute({
    "function": "get_product",
    "category_id": "15",
    "product_id": "11"
})
```

**返回示例：**
```json
{
    "success": true,
    "product_id": "11",
    "category_id": "15",
    "url": "https://www.lzljglobal.com/col15/11",
    "title": "国窖1573·澳网纪念版",
    "main_image": "https://www.lzljglobal.com/upload/image/2025-10/col15/1761546960466.png",
    "images": [
        {
            "url": "https://www.lzljglobal.com/upload/image/2025-10/col15/1761546960466.png",
            "alt": "国窖1573·澳网纪念版"
        },
        ...
    ],
    "specifications": {
        "alcohol_content": "40%vol",
        "specification": "750ml"
    },
    "description": "中国白酒与世界顶级网球赛事的跨界之作，为纪念泸州老窖与澳大利亚网球公开赛达成战略合作特别酿制..."
}
```

### 4. 搜索产品 (search_products)

在产品标题中搜索关键词，可限制在特定分类或跨所有分类搜索。

**参数：**
- `query` (必需): 搜索关键词
- `category_id` (可选): 限制在特定分类中搜索

**示例：**
```python
# 在所有分类中搜索
result = await execute({
    "function": "search_products",
    "query": "国窖"
})

# 在特定分类中搜索
result = await execute({
    "function": "search_products",
    "query": "经典",
    "category_id": "15"
})
```

## 产品分类

| 分类ID | 分类名称 |
|--------|----------|
| 15 | 国窖1573 |
| 16 | 泸州老窖头曲 |
| 17 | 泸州老窖二曲 |
| 18 | 泸州老窖特曲 |

## 技术说明

- 本技能使用 aiohttp 直接抓取HTML页面并解析
- 网站为静态HTML，无需处理JavaScript动态加载
- 产品列表URL格式：`/col{category_id}/list` (第1页) 或 `/col{category_id}/list_{page}` (后续页)
- 产品详情URL格式：`/col{category_id}/{product_id}`

## 错误处理

所有API调用都返回包含 `success` 字段的字典：
- `success: true` - 调用成功
- `success: false` - 调用失败，包含 `error` 字段说明错误原因

## 使用限制

- 请合理控制请求频率，避免对服务器造成过大压力
- 产品数据来自公开网站，请遵守网站使用条款