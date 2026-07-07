# 财富500强情报中心 (Caifuzhongwen.com) 访问技能

## 概述

本技能用于访问财富中文网的财富500强情报中心网站（www.caifuzhongwen.com），获取世界500强和中国500强企业排行榜数据及企业详细信息。

## 功能说明

### 1. get_rankings - 获取排行榜

获取完整的企业排行榜列表。

**参数：**
- `list_type`: 排行榜类型
  - `global500`: 世界500强（默认）
  - `china500`: 中国500强
- `year`: 年份（如 2024）

**返回数据：**
- 排名
- 公司名称（中英文）
- 营收（百万美元）
- 公司详情链接

**示例：**
```python
# 获取2024年世界500强榜单
execute({
    'function': 'get_rankings',
    'list_type': 'global500',
    'year': 2024
})

# 获取2023年中国500强榜单
execute({
    'function': 'get_rankings',
    'list_type': 'china500',
    'year': 2023
})
```

### 2. get_company_detail - 获取企业详情

根据公司ID获取详细的企业信息，包括财务数据、基本资料等。

**参数：**
- `company_id`: 公司ID（从排行榜中获取，如 '252'）
- `year`: 年份（默认 2024）
- `list_type`: 排行榜类型（默认 'global500'）

**返回数据：**
- 公司名称（中英文）
- 排名
- 年份
- 营收、利润、资产、股东权益
- 同比增长率
- 净利润率、净资产收益率
- 国家、行业、总部地址
- 员工数量、官网
- 历年数据链接

**示例：**
```python
# 获取中国铁道建筑集团2024年详情
execute({
    'function': 'get_company_detail',
    'company_id': '252',
    'year': 2024,
    'list_type': 'global500'
})
```

### 3. get_company_by_rank - 按排名获取企业

根据排名位置直接获取企业详情。

**参数：**
- `rank`: 排名数字（1-500）
- `year`: 年份
- `list_type`: 排行榜类型

**示例：**
```python
# 获取2024年世界500强第1名企业详情
execute({
    'function': 'get_company_by_rank',
    'rank': 1,
    'year': 2024,
    'list_type': 'global500'
})
```

### 4. search_company - 搜索企业

按企业名称搜索（支持中英文模糊匹配）。

**参数：**
- `query`: 搜索关键词
- `year`: 年份
- `list_type`: 排行榜类型
- `limit`: 返回结果数量（默认10）

**示例：**
```python
# 搜索名称包含"银行"的企业
execute({
    'function': 'search_company',
    'query': '银行',
    'year': 2024,
    'limit': 10
})

# 搜索英文名称包含"apple"的企业
execute({
    'function': 'search_company',
    'query': 'apple',
    'year': 2024
})
```

## 数据来源

所有数据均来自财富500强情报中心网站直接HTTP请求解析，无需浏览器自动化。

**URL模式：**
- 排行榜: `/fortune500/paiming/{list_type}/{year}_{榜单名称}.htm`
- 企业详情: `/fortune500/gongsi/{list_type}/{year}/{company_id}.htm`

## 注意事项

1. 网站可能限流，建议请求间隔不低于1秒
2. 企业ID与公司名称相关，但不是简单的排名数字
3. 历史数据可追溯至2016年左右
4. 所有金额单位均为百万美元