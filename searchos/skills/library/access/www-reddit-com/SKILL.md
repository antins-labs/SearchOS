---
name: www-reddit-com
description: 通过官方 RSS 订阅读取 Reddit 公开板块帖子列表。无需认证。
metadata:
  searchos-category: access
  host: www.reddit.com
---

# www-reddit-com

通过 Reddit 官方 RSS 订阅读取公开板块帖子列表。无需认证，返回标题、作者、摘要、链接等基本信息。

## 能力说明

**已验证可用**：
- `reddit_rss.py`：读取指定板块的 RSS 订阅，返回帖子列表

**不可用**：
- PullPush API（归档服务）频繁 429/超时，不稳定，不作为公开能力
- 官方 JSON API（www.reddit.com/*.json）返回 403，阻止未认证请求
- 官方搜索 API 返回 403
- 评论内容：RSS 不提供评论

**限制**：
- RSS 仅提供有限的帖子，排序由 Reddit 决定
- 可能遇到 429 限流，需稍后重试（等待数分钟后重试）
- 字段有限：标题、作者、链接、发布时间、摘要

## 命令

### reddit_rss.py - 读取板块帖子

```bash
python scripts/reddit_rss.py --subreddit Python --limit 25 --output result.json
python scripts/reddit_rss.py -s rust -l 10
```

**参数**：
- `--subreddit, -s`：板块名称（必填），可带或不带 `r/` 前缀
- `--limit, -l`：返回数量，1-100（默认 25）
- `--output, -o`：输出文件路径（默认 stdout）

**输出格式**：

```json
{
  "success": true,
  "subreddit": "Python",
  "count": 25,
  "source": "reddit_rss",
  "source_url": "https://www.reddit.com/r/Python/.rss?limit=25",
  "records": [
    {
      "id": "post_id",
      "title": "帖子标题",
      "author": "作者用户名",
      "subreddit": "Python",
      "url": "https://www.reddit.com/r/Python/comments/...",
      "source_url": "https://www.reddit.com/r/Python/comments/...",
      "published": "2026-10-12T10:00:00+00:00",
      "updated": "2026-10-12T11:00:00+00:00",
      "content": "完整内容或摘要",
      "summary": "摘要文本"
    }
  ],
  "pagination": {
    "complete": false,
    "note": "RSS feed provides limited results; sorting determined by Reddit; may encounter 429 rate limits"
  }
}
```

**错误处理**：
- 无效板块名（非 2-21 位字母数字下划线）：参数错误，退出码 1
- limit 超出 1-100 范围：参数错误，退出码 1
- 网络错误、404、登录页面：返回 `success: false` + 错误信息，退出码 1
- 空结果（板块无帖子）：返回空 `records` 数组，退出码 0

## 依赖

仅使用 Python 标准库，无需额外安装。

## 迁移说明

旧版 `scripts/run.py` 已改为 RSS 兼容入口，仅支持 `get_subreddit` 功能（转发到官方 RSS）。`scripts/source.py` 为历史实现，不作为公开功能。本技能仅提供官方 RSS 阅读能力。
