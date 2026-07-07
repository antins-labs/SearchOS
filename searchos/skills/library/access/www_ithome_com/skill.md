# IT之家文章提取器

从 IT之家 (ithome.com) 网站提取文章内容、元数据和图片。

## 功能

### fetch_article

获取单篇 IT之家文章的完整内容。

**参数:**
- `url` (必需): IT之家文章 URL，格式如 `https://www.ithome.com/0/663/928.htm`
- `format_summary` (可选): 是否生成可读的文本摘要，默认 false

**返回数据:**
- `success`: 是否成功提取
- `title`: 文章标题
- `description`: 文章摘要（meta description）
- `keywords`: 关键词标签
- `date`: 发布日期时间（格式：YYYY/MM/DD HH:MM:SS）
- `author`: 作者姓名
- `editor`: 责编姓名
- `source`: 来源（通常为"IT之家"）
- `content`: 文章正文内容（纯文本）
- `images`: 图片列表，包含 URL、alt 文本、title
- `category_id`: 分类 ID（从 URL 提取）
- `article_id`: 文章 ID（从 URL 提取）
- `summary`: 格式化的摘要文本（当 format_summary=true 时）

**示例:**
```python
result = await execute({
    'function': 'fetch_article',
    'url': 'https://www.ithome.com/0/663/928.htm',
    'format_summary': True
})
```

### fetch_articles

批量获取多篇文章，支持并发请求。

**参数:**
- `urls` (必需): IT之家文章 URL 列表

**返回数据:**
- `success`: 总体执行状态
- `total`: 总数量
- `successful`: 成功数量
- `failed`: 失败数量
- `articles`: 文章数据列表

**示例:**
```python
result = await execute({
    'function': 'fetch_articles',
    'urls': [
        'https://www.ithome.com/0/663/928.htm',
        'https://www.ithome.com/0/521/657.htm'
    ]
})
```

## URL 格式

IT之家文章 URL 格式为：
```
https://www.ithome.com/{category_id}/{article_id}.htm
```

例如：
- `https://www.ithome.com/0/663/928.htm` (category_id=663, article_id=928)
- `https://www.ithome.com/0/521/657.htm` (category_id=521, article_id=657)

## 提取字段说明

| 字段 | 说明 | 示例值 |
|------|------|--------|
| title | 文章标题 | "2499 元起，小米 Redmi K60 发布：..." |
| date | 发布时间 | "2022/12/27 20:03:58" |
| author | 作者 | "汪淼" |
| editor | 责编 | "汪淼" |
| source | 来源 | "IT之家" |
| keywords | 关键词 | "Redmi K60" |
| content | 正文内容 | 完整文章内容（纯文本） |
| images | 图片列表 | [{"url": "...", "alt": ""}] |

## 技术实现

- 使用 aiohttp 进行异步 HTTP 请求
- 使用 BeautifulSoup 进行 HTML 解析
- 提取 `<h1>` 标签作为标题
- 提取 `#paragraph` 元素作为正文内容
- 通过特定的 span ID（pubtime_baidu, author_baidu, editor_baidu）提取元数据
- 支持 lazy-load 图片（data-original 属性）

## 错误处理

- 无效域名返回错误信息
- URL 格式不正确返回错误信息
- HTTP 错误（如 404, 500）返回状态码
- 网络超时返回超时错误
- 所有错误不会抛出异常，而是返回包含 `success: false` 和 `error` 字段的结果

## 注意事项

- 内容提取为纯文本，会移除 HTML 标签
- 图片 URL 会自动转换为绝对路径
- 部分文章可能缺少某些元数据字段（作者、责编等）
- 正文内容包含完整的 \n 分隔符