# 阳光高考 (gaokao.chsi.com.cn) 数据访问技能

## 概述

本技能用于从阳光高考平台 (gaokao.chsi.com.cn) 获取高考相关政策公告、录取分数线、考生分数分布等数据。

## 功能说明

### 1. get_article - 获取文章信息

从阳光高考网站获取文章元数据，包括标题、日期、来源以及外部数据源链接。

**参数:**
- `url`: 文章URL (必需)

**示例:**
```python
result = await execute({
    "function": "get_article",
    "url": "https://gaokao.chsi.com.cn/gkxx/zc/ss/202008/20200817/1964457141.html"
})
```

**返回数据:**
- `page_title`: 页面标题
- `article_title`: 文章标题
- `date`: 发布日期
- `source`: 来源机构
- `province`: 省份
- `category`: 分类
- `external_links`: 外部数据源链接列表
- `has_data`: 是否包含数据链接

### 2. get_external_data - 获取外部数据

从外部教育考试机构网站（如北京教育考试院 bjeea.cn）获取表格数据，包括投档线、分数分布等。

**参数:**
- `url`: 外部数据源URL (必需)

**示例:**
```python
result = await execute({
    "function": "get_external_data",
    "url": "https://www.bjeea.cn/html/gkgz/tzgg/2020/0817/76309.html"
})
```

**返回数据:**
- `tables`: 表格数据数组
  - `headers`: 表头
  - `rows`: 行数据
  - `data`: 字典格式的数据（每行为一个字典）
  - `total_rows`: 总行数
- `table_count`: 表格数量
- `total_rows`: 所有表格总行数

### 3. search_list - 搜索公告列表

按分类和省份浏览最新公告列表。

**参数:**
- `category`: 分类代码，默认 'zc' (政策)
- `province`: 省份代码，默认 'ss' (综合)

**常见省份代码:**
- `ss`: 省市综合
- `bj`: 北京
- `sh`: 上海
- `js`: 江苏
- `gd`: 广东
- `sc`: 四川
- 更多省份代码请参考网站结构

**示例:**
```python
result = await execute({
    "function": "search_list",
    "category": "zc",
    "province": "ss"
})
```

**返回数据:**
- `articles`: 文章列表
  - `title`: 文章标题
  - `url`: 文章URL
  - `date`: 发布日期
- `total`: 总数

## 使用场景

### 场景1: 获取某省高考投档线数据

1. 使用 `search_list` 查找该省相关公告
2. 使用 `get_article` 获取文章信息和外部数据链接
3. 使用 `get_external_data` 获取完整的投档线表格数据

### 场景2: 获取某年高考分数分布

1. 直接通过已知URL调用 `get_article`
2. 解析返回的 `external_links` 找到数据源
3. 调用 `get_external_data` 获取数据

## 技术说明

- 使用 httpx 进行HTTP请求
- 使用 BeautifulSoup 解析HTML
- 自动处理中文编码
- 提取表格数据并转换为结构化格式
- 支持多省份教育考试机构网站数据解析

## 限制

- 部分文章可能只包含外部链接引用，无实际内容
- 外部数据源网站可能需要额外处理
- 表格数据默认限制返回前100行

## 注意事项

- 网站数据实时更新，具体URL结构可能变化
- 外部数据源网站（如各省市教育考试院）需要单独适配
- 请遵守网站robots.txt和使用条款