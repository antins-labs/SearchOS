# Fox围棋新闻提取器

从野狐围棋网站（www.foxwq.com）抓取围棋新闻文章和列表。

## 功能说明

该技能提供三个主要功能：

### 1. 获取单篇文章 (get_article)

获取指定文章的详细内容，包括：
- 文章标题
- 作者
- 发布时间
- 阅读量（点击数）
- 文章正文
- 相关推荐新闻
- 关键词

**参数：**
- `article_id`: 文章ID（必需）

**示例：**
```python
params = {
    "function": "get_article",
    "article_id": "14371"
}
```

**返回示例：**
```json
{
    "success": true,
    "article": {
        "article_id": "14371",
        "url": "https://www.foxwq.com/news/14371.html",
        "title": "吴清源杯参赛阵容确定 李赫俞俐均获外卡",
        "author": "菜菜子",
        "publish_time": "2023-06-01 19:25",
        "views": 11302,
        "keywords": "吴清源杯,吴侑珍,俞俐均",
        "content": "第6届吴清源杯世界女子围棋赛首轮比赛...",
        "content_length": 820,
        "related_news": ["中韩女子棋界最强5对5第三场..."]
    }
}
```

### 2. 获取新闻列表 (list_news)

获取网站新闻列表，支持分页。

**参数：**
- `page`: 页码（可选，默认为1）

**示例：**
```python
params = {
    "function": "list_news",
    "page": 1
}
```

**返回示例：**
```json
{
    "success": true,
    "news_list": [
        {
            "article_id": "16784",
            "title": "韩国GS加德士杯决赛第二局朴廷桓再负申旻埈",
            "url": "https://www.foxwq.com/news/listid/id/16784.html",
            "date": "2026-03-15"
        }
    ],
    "page": 1,
    "total_pages": 642,
    "has_next": true,
    "has_prev": false,
    "count": 20
}
```

### 3. 获取文章评论 (get_comments)

获取指定文章的用户评论。

**参数：**
- `article_id`: 文章ID（必需）
- `page`: 评论页码（可选，默认为0）

**示例：**
```python
params = {
    "function": "get_comments",
    "article_id": "14371"
}
```

**返回示例：**
```json
{
    "success": true,
    "article_id": "14371",
    "page": 0,
    "comment_count": 1,
    "comments": [
        {
            "username": "陈金有",
            "time": "2023-06-10 17:49",
            "content": "为啥没有黑妹妹，俺的最爱",
            "likes": 1
        }
    ],
    "comments_fetched": 1
}
```

## 网站背景

野狐围棋（foxwq.com）是一个专注于围棋资讯的中国网站，主要内容包括：
- 围棋赛事新闻
- 职业棋手资讯
- 比赛结果和赛程
- 围棋文化相关内容

## 注意事项

1. 文章URL格式：`https://www.foxwq.com/news/{article_id}.html`
2. 列表页URL格式：`https://www.foxwq.com/news/index/p/{page}.html`
3. 评论API：`/news/ajaxGetCommentPc.html?page={page}&newsid={article_id}`
4. 部分旧文章可能不存在或已删除
5. 网站使用中文，返回内容均为中文

## 数据来源

所有数据直接通过HTTP请求从foxwq.com抓取，使用BeautifulSoup解析HTML内容。