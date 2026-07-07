# m.onezh.com 展会信息查询

## 概述

本技能用于从第一展会网（m.onezh.com）获取中国展会信息，包括展会详情、展会列表搜索、关键词搜索和日期范围搜索等功能。

## 数据源

- **网站**: m.onezh.com（第一展会网手机版）
- **内容**: 全国各地展会信息，包括展会名称、时间、地点、主办方、联系方式等

## 功能说明

### 1. 获取展会详情 (get_detail)

获取指定展会的详细信息。

**参数**:
- `exhibition_id`: 展会ID（必需）

**示例返回数据**:
```json
{
  "success": true,
  "exhibition_id": "85169",
  "title": "2025中国华夏家博会(北京)",
  "start_date": "2025-05-30周五",
  "end_date": "2025-06-01周日",
  "city": "北京-朝阳区",
  "industry": "建筑、装潢、五金",
  "venue": "北京国家会议中心",
  "organizer": "商务部外贸发展局、上海装饰装修行业协会",
  "email": "kefuzhongxin@51jiabo.com",
  "phone": "400-6188-555"
}
```

### 2. 搜索展会列表 (search)

根据条件搜索展会列表。

**参数**:
- `city_id`: 城市ID（0表示全部）
- `industry_id`: 行业ID（0表示全部）
- `venue_id`: 场馆ID（0表示全部）
- `start_date`: 开始日期（格式YYYYMMDD）
- `end_date`: 结束日期（格式YYYYMMDD）
- `page`: 页码

**城市ID参考**:
- 0: 全国
- 1: 北京
- 2: 上海
- 其他城市请参考网站

**示例**:
```
// 搜索北京2025年5月的展会
{
  "function": "search",
  "city_id": "1",
  "start_date": "20250501",
  "end_date": "20250531"
}
```

### 3. 关键词搜索 (search_by_keyword)

根据关键词搜索展会。

**参数**:
- `keyword`: 搜索关键词

**示例**:
```
{
  "function": "search_by_keyword",
  "keyword": "珠宝"
}
```

### 4. 日期范围搜索 (search_by_date)

按日期范围搜索展会。

**参数**:
- `start_date`: 开始日期（格式YYYYMMDD）
- `end_date`: 结束日期（格式YYYYMMDD）
- `city_id`: 城市ID（可选）

**示例**:
```
{
  "function": "search_by_date",
  "start_date": "20250601",
  "end_date": "20250630"
}
```

## 返回字段说明

### 展会详情字段

| 字段 | 说明 |
|------|------|
| exhibition_id | 展会ID |
| title | 展会名称 |
| start_date | 开展日期 |
| end_date | 结束日期 |
| city | 举办城市 |
| industry | 所属行业 |
| venue | 举办地点/场馆 |
| organizer | 主办单位 |
| undertaker | 承办单位 |
| email | 联系邮箱 |
| phone | 联系电话 |
| website | 官方网站 |
| introduction | 展会介绍 |
| exhibits | 展品范围 |
| image | 展会图片/Logo |
| view_count | 浏览量 |

### 展会列表字段

| 字段 | 说明 |
|------|------|
| exhibitions | 展会列表 |
| total_on_page | 当前页展会数量 |
| current_page | 当前页码 |
| has_next_page | 是否有下一页 |

## 错误处理

当请求出错时，返回数据包含:
- `success`: false
- `error`: 错误描述
- `error_code`: 错误代码

常见错误代码:
- `MISSING_EXHIBITION_ID`: 缺少展会ID
- `MISSING_KEYWORD`: 缺少搜索关键词
- `MISSING_FUNCTION`: 缺少功能参数
- `UNKNOWN_FUNCTION`: 未知功能名
- `FETCH_ERROR`: 网络请求失败
- `SEARCH_ERROR`: 搜索失败

## 使用建议

1. 获取展会详情前，先通过搜索功能找到展会ID
2. 使用日期范围搜索可以获取特定时间段的展会
3. 城市ID可用于筛选特定城市的展会
4. 列表页每页最多显示40条记录

## 数据来源

所有数据来自 m.onezh.com（第一展会网），仅供查询参考使用。