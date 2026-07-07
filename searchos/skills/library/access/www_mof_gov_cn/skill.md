# 财政部网站访问技能 (Ministry of Finance of China Access Skill)

## 概述

本技能用于访问中华人民共和国财政部官方网站 (www.mof.gov.cn)，重点提供对"中央对地方转移支付管理平台"的结构化数据访问，以及财政新闻和政策文档的获取能力。

## 功能说明

### 1. list_transfer_categories - 列出转移支付类别

获取中央对地方转移支付管理平台的所有支付类别，包括：
- 一般性转移支付（均衡性转移支付、重点生态功能区转移支付等）
- 专项转移支付（国家重点档案专项资金、支持学前教育发展资金等）

**使用示例：**
```python
result = await execute({
    'function': 'list_transfer_categories'
})
```

**返回数据包含：**
- 类别名称
- 类别URL
- 类别类型（一般性/专项）
- 类别路径

### 2. list_category_documents - 列出类别文档

获取特定转移支付类别下的所有政策文档和通知列表。

**参数：**
- `category_url` (必需): 类别页面的完整URL

**使用示例：**
```python
result = await execute({
    'function': 'list_category_documents',
    'category_url': 'http://www.mof.gov.cn/zhuantihuigu/cczqzyzfglbf/ybxzyzf_7774/jhxxyzf/'
})
```

**返回数据包含：**
- 文档标题
- 文档URL
- 文档ID
- 发布日期
- 分页信息

### 3. list_news - 列出财政新闻

获取财政部新闻列表，支持分页浏览。

**参数：**
- `page` (可选): 页码，从0开始

**使用示例：**
```python
# 获取第一页
result = await execute({
    'function': 'list_news',
    'page': 0
})

# 获取第二页
result = await execute({
    'function': 'list_news',
    'page': 1
})
```

**返回数据包含：**
- 新闻文章列表
- 当前页码
- 总页数（如果可获取）
- 每篇文章的标题、URL和日期

### 4. get_article - 获取文章详情

获取文章的完整内容和元数据。

**参数：**
- `url` (必需): 文章的完整URL

**使用示例：**
```python
result = await execute({
    'function': 'get_article',
    'url': 'http://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/202309/t20230904_3905364.htm'
})
```

**返回数据包含：**
- 标题
- 发布日期
- 来源
- 完整文本内容
- 段落数量
- 附件列表（如有）
- 文档ID

### 5. search_site - 搜索文档

按类别名称关键词搜索相关文档。

**参数：**
- `category` (可选): 类别名称关键词筛选
- `max_results` (可选): 最大返回结果数，默认20

**使用示例：**
```python
# 搜索均衡性相关的所有文档
result = await execute({
    'function': 'search_site',
    'category': '均衡性',
    'max_results': 30
})
```

## 典型使用场景

### 场景1：获取转移支付政策列表
```python
# 1. 先获取所有类别
categories = await execute({'function': 'list_transfer_categories'})

# 2. 选择感兴趣的类别
target_category = None
for cat in categories['categories']:
    if '均衡性转移支付' in cat['name']:
        target_category = cat
        break

# 3. 获取该类别下的所有文档
if target_category:
    documents = await execute({
        'function': 'list_category_documents',
        'category_url': target_category['url']
    })
```

### 场景2：追踪最新财政新闻
```python
# 获取最新财政新闻
news = await execute({
    'function': 'list_news',
    'page': 0
})

# 查看详情
if news['success'] and news['articles']:
    first_article = news['articles'][0]
    detail = await execute({
        'function': 'get_article',
        'url': first_article['url']
    })
```

## 数据结构

### 文章对象 (Article)
```json
{
  "title": "国务院关于财政转移支付情况的报告",
  "url": "http://www.mof.gov.cn/zhengwuxinxi/...",
  "document_id": "3905364",
  "date": "2023-09-04"
}
```

### 类别对象 (Category)
```json
{
  "name": "均衡性转移支付",
  "url": "http://www.mof.gov.cn/zhuantihuigu/cczqzyzfglbf/ybxzyzf_7774/jhxxyzf/",
  "type": "一般性转移支付",
  "path": "ybxzyzf_7774/jhxxyzf/"
}
```

## 技术说明

- 本技能使用直接HTTP请求访问网站，无需浏览器自动化
- 所有请求包含适当的User-Agent头部以确保兼容性
- 支持HTTP和HTTPS两种协议
- 自动处理相对URL转换为绝对URL
- 自动解析日期、文档ID等元数据

## 错误处理

所有函数返回统一的响应格式：

**成功响应：**
```json
{
  "success": true,
  "total": 25,
  "articles": [...]
}
```

**错误响应：**
```json
{
  "success": false,
  "error": "错误描述信息"
}
```

## 注意事项

1. 网站可能限制了访问频率，建议在大量请求时添加适当延迟
2. 部分旧文档可能已被删除或移动，会返回404错误
3. 文章标题可能包含网站名称后缀，已自动清理
4. 日期解析优先从页面内容提取，其次从URL推断

## 更新日期

本技能最后更新于2024年，基于网站当时的结构开发。如网站结构发生变化，可能需要更新解析逻辑。