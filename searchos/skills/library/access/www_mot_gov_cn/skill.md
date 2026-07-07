# 中国交通运输部铁路统计数据访问技能

## 概述

本技能用于访问中华人民共和国交通运输部官方网站（www.mot.gov.cn）发布的全国铁路主要指标月度统计数据。

**重要发现**：经过详细探测，发现该网站的统计数据以**PNG图片**形式嵌入网页之中，而非结构化的HTML表格或JSON数据。这是中国政府网站确保数据展示一致性的常见做法。

## 网站结构

### 数据页面层级

```
www.mot.gov.cn/shuju/                          # 数据中心首页
└── tongjishuju/                               # 统计数据目录
    └── tielu/                                 # 铁路统计
        ├── index.html                         # 第1页文章列表
        ├── index_1.html                       # 第2页
        ├── index_2.html                       # 第3页
        └── YYYYMM/tYYYYMMDD_articleid.html    # 文章详情页
            └── W0{16位随机字符}.png            # 统计图片
```

### 文章列表结构

每个列表页显示约15篇左右的月度统计报告，包含：
- 文章标题（如"2026年1月份全国铁路主要指标完成情况"）
- 发布日期
- 文章链接

### 文章详情页结构

每篇文章包含：
- 标题（meta[name="ArticleTitle"]）
- 发布日期（meta[name="PubDate"]）
- 来源（meta[name="ContentSource"]）
- 统计数据图片（PNG格式）

## API调用示例

### 1. 获取最新统计文章

```python
result = await execute({
    "function": "list_latest",
    "count": 5,
    "include_details": true
})
```

返回结果示例：
```json
{
  "success": true,
  "articles": [
    {
      "title": "2026年4月份全国铁路主要指标完成情况",
      "url": "https://www.mot.gov.cn/shuju/tongjishuju/tielu/202605/t20260519_4205752.html",
      "pub_date": "2026-05-12",
      "source": "国家铁路局",
      "image_url": "https://www.mot.gov.cn/shuju/tongjishuju/tielu/202605/W020260519xxxxx.png"
    }
  ]
}
```

### 2. 分页获取文章列表

```python
result = await execute({
    "function": "list_articles",
    "page": 1,
    "limit": 20
})
```

### 3. 按月份搜索

```python
result = await execute({
    "function": "search_by_month",
    "year": 2026,
    "month": 1
})
```

### 4. 获取文章详情

```python
result = await execute({
    "function": "get_article",
    "url": "https://www.mot.gov.cn/shuju/tongjishuju/tielu/202602/t20260215_4200440.html"
})
```

### 5. 下载统计图片

```python
result = await execute({
    "function": "get_image",
    "url": "https://www.mot.gov.cn/shuju/tongjishuju/tielu/202602/t20260215_4200440.html",
    "include_base64": true
})
```

## 数据提取注意事项

### 图片格式分析

探测发现的统计图片特征：

| 属性 | 典型值 |
|------|--------|
| 尺寸 | 700×300 像素 |
| 格式 | PNG (RGB/RGBA) |
| 文件大小 | 17KB - 85KB |
| 文件名 | W0{YYMMDD}{随机ID}.png |

### OCR提取建议

由于数据以图片形式发布，需要OCR处理才能提取数值数据。推荐方案：

1. **PaddleOCR** - 国产开源OCR，中文识别效果最佳
2. **百度OCR API** - 商业级中文OCR服务
3. **Tesseract + chi_sim** - 开源方案，需安装中文语言包

示例OCR流程：
```python
from PIL import Image
import pytesseract

# 下载图片后
img = Image.open('statistics.png')
text = pytesseract.image_to_string(img, lang='chi_sim+eng')
```

### 数据字段说明

铁路主要指标通常包括：

| 指标名称 (中文) | 英文名称 | 单位 |
|----------------|---------|------|
| 旅客发送量 | Passenger Departure | 万人 |
| 旅客周转量 | Passenger Turnover | 亿人公里 |
| 货物发送量 | Freight Departure | 万吨 |
| 货物周转量 | Freight Turnover | 亿吨公里 |
| 总换算周转量 | Total Turnover | 亿吨公里 |

## 限制说明

### 技术限制

1. **数据格式**：统计数据为图片，非结构化文本
2. **OCR准确性**：依赖OCR质量，可能存在识别误差
3. **历史数据**：网站仅保留近期数据，深层历史数据可能不可访问

### 访问限制

| 类型 | 值 |
|------|-----|
| 每秒请求数 | 2 |
| 每分钟请求数 | 60 |

### 数据时效性

- 月度统计通常在次月中旬发布
- 数据更新频率：每月
- 数据来源：国家铁路局

## 错误处理

技能返回统一的错误格式：

```json
{
  "success": false,
  "error": "错误描述信息",
  "url": "请求的URL（如适用）"
}
```

常见错误：
- `HTTP 404`: 文章不存在或URL错误
- `HTTP 500`: 服务器临时错误，建议重试
- `Missing required parameter: url`: 缺少必需参数

## 探测发现摘要

经过系统性探测，确认以下发现：

1. ✅ 文章列表可通过 `/shuju/tongjishuju/tielu/` 访问
2. ✅ 分页使用 `index_N.html` 格式
3. ✅ 每篇文章包含一个PNG格式的统计表格图片
4. ✅ 图片命名遵循 `W0{时间戳}{随机ID}.png` 格式
5. ⚠️ 统计数据以图片形式发布，需要OCR处理
6. ⚠️ 图像内容为中文表格，需支持中文的OCR工具

## 更新历史

- **2024-01**: 初始版本，支持文章列表、详情查询、图片下载功能