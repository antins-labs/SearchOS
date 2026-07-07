# 四川省人事考试中心 (SCPTA) 访问技能

本技能用于从四川省人力资源和社会保障厅人事考试专栏 (www.scpta.com.cn) 获取各类人事考试公告、通知和招录信息。

## 网站简介

四川省人事考试中心网站是四川省官方人事考试信息发布平台，提供：
- 公务员招录公告
- 事业单位招聘通知
- 专业技术人员资格考试信息
- "三支一扶"等专项计划招录信息
- 各类人事考试报名、成绩查询等服务

## 功能说明

### 1. 获取文章详情 (get_article)

根据文章ID获取完整的公告内容、附件信息、发布日期等。

**参数:**
- `news_id`: 文章ID（必填），32位十六进制字符串

**返回示例:**
```json
{
  "success": true,
  "id": "0a5c2590651844b7a2eaf3ee6e9f23e8",
  "title": "四川省高级人民法院2025年公开招聘聘用制书记员公告",
  "content": "公告正文...",
  "publish_date": "2025年5月6日",
  "source": "四川省高级人民法院",
  "attachments": [
    {
      "title": "岗位和条件要求一览表",
      "url": "https://www.scpta.com.cn/download-xxx"
    }
  ],
  "images": [],
  "url": "https://www.scpta.com.cn/front/News/info/0a5c2590651844b7a2eaf3ee6e9f23e8"
}
```

### 2. 列出公告 (list_articles)

获取指定分类的公告列表或首页最新公告。

**参数:**
- `category_id`: 分类ID（可选）
- `page`: 页码（可选，默认1）

**已知分类ID:**
- `33` - 通知公告
- `56` - 公务员招录
- `72` - 三支一扶

**返回示例:**
```json
{
  "success": true,
  "category_id": "33",
  "page": 1,
  "total": 30,
  "items": [
    {
      "id": "f856682b05294fa7a1f3048a19b341d2",
      "title": "四川省人事考试中心关于开展专业技术人员职业资格证书直邮工作的通知",
      "url": "https://www.scpta.com.cn/front/News/info/f856682b05294fa7a1f3048a19b341d2",
      "category_id": "33"
    }
  ]
}
```

## 使用示例

### Python 示例

```python
import asyncio
from executor import execute

async def main():
    # 获取单篇文章
    result = await execute({
        "function": "get_article",
        "news_id": "0a5c2590651844b7a2eaf3ee6e9f23e8"
    })
    print(f"标题: {result.get('title')}")
    print(f"发布日期: {result.get('publish_date')}")
    
    # 列出通知公告
    result = await execute({
        "function": "list_articles",
        "category_id": "33"
    })
    for item in result.get("items", []):
        print(f"- {item['title']}")

asyncio.run(main())
```

## 注意事项

1. **文章ID获取**: 可以通过 `list_articles` 获取文章列表后，从返回的 `id` 字段获取文章ID。

2. **附件下载**: 文章中的附件URL可以直接访问下载，通常为PDF、Word文档等格式。

3. **日期格式**: 发布日期以中文格式返回（如"2025年5月6日"），可能需要程序解析转换。

4. **内容长度**: 公告内容可能较长，建议根据需要截取或分页显示。

5. **字符编码**: 网站使用UTF-8编码，中文内容可正常获取。

## 技术说明

- 该网站为服务端渲染HTML，无需JavaScript即可获取完整内容
- 无需Cookie或Session维护
- 支持分页访问（每页约25-30条）
- 请求频率建议控制在合理范围内，避免对服务器造成压力