# 文化和旅游部数据服务栏目访问技能

本技能用于从中华人民共和国文化和旅游部数据服务栏目 (sjfw.mct.gov.cn) 提取旅游相关数据。

## 数据类型

网站提供以下六类数据：

| type_id | 名称 | 说明 |
|---------|------|------|
| 10 | 国家5A级旅游景区 | 全国5A级景区名单 |
| 11 | 五星级旅游饭店 | 全国五星级酒店名单 |
| 54 | 国家级旅游度假区 | 国家级度假区列表 |
| 135 | 国家级滑雪旅游度假地 | 国家级滑雪度假地名单 |
| 138 | 国家级旅游休闲街区 | 国家级休闲街区名单 |
| 143 | 国家工业旅游示范基地 | 工业旅游示范基地名单 |

## 功能说明

### 1. list_types - 列出数据类型

列出所有可用的数据类型及其名称。

```json
{
  "function": "list_types"
}
```

返回示例：
```json
{
  "success": true,
  "data_types": [
    {"type_id": 10, "name": "国家5A级旅游景区"},
    {"type_id": 11, "name": "五星级旅游饭店"},
    ...
  ]
}
```

### 2. fetch - 获取全部数据

获取指定类型的全部数据列表。

```json
{
  "function": "fetch",
  "type_id": 54
}
```

返回示例：
```json
{
  "success": true,
  "type_id": 54,
  "type_name": "国家级旅游度假区",
  "total_count": 85,
  "data": [
    {
      "id": 34005,
      "name": "密云古北水镇国际休闲旅游度假区",
      "province_code": 110000,
      "province_name": "北京",
      "year": "2024",
      "grade": "",
      "code": "",
      "place": "",
      "created_at": "2024-06-15 15:53:00"
    },
    ...
  ]
}
```

### 3. count - 获取数据条数

仅获取指定类型的数据总数，不返回详细数据。

```json
{
  "function": "count",
  "type_id": 10
}
```

返回示例：
```json
{
  "success": true,
  "type_id": 10,
  "type_name": "国家5A级旅游景区",
  "total_count": 359
}
```

### 4. filter_province - 按省份筛选

按省份名称筛选数据。

```json
{
  "function": "filter_province",
  "type_id": 54,
  "province_name": "浙江"
}
```

返回示例：
```json
{
  "success": true,
  "type_id": 54,
  "type_name": "国家级旅游度假区",
  "province_filter": "浙江",
  "total_count": 9,
  "data": [...]
}
```

### 5. search - 按名称搜索

按名称关键词搜索数据。

```json
{
  "function": "search",
  "type_id": 10,
  "name_keyword": "长城"
}
```

返回示例：
```json
{
  "success": true,
  "type_id": 10,
  "type_name": "国家5A级旅游景区",
  "search_keyword": "长城",
  "total_count": 5,
  "data": [
    {
      "id": 34782,
      "name": "八达岭—慕田峪长城旅游区2007年",
      "province_name": "北京",
      ...
    },
    ...
  ]
}
```

## 数据字段说明

每条数据记录包含以下字段：

- `id`: 数据记录ID
- `name`: 名称
- `province_code`: 省份代码（行政区划代码）
- `province_name`: 省份名称
- `year`: 批次年份
- `grade`: 等级（部分数据类型使用）
- `code`: 编号（部分数据类型使用）
- `place`: 地址（部分数据类型使用，如五星级酒店）
- `created_at`: 数据创建时间

## 技术说明

网站采用 Nuxt.js 进行服务端渲染，数据嵌入在页面的 `window.__NUXT__` 对象中。本技能使用 Playwright 浏览器自动化工具来提取这些数据。

## 注意事项

1. 数据来源于文化和旅游部官方数据服务，截止日期各不相同
2. 部分数据字段（如 grade、code、place）可能为空，取决于数据类型
3. 数据按省份分组并排序展示