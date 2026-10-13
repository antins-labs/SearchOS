# Reddit 能力地图

## 已验证可用

### Reddit 官方 RSS

| 功能 | 命令 | 端点 | 状态 |
|------|------|------|------|
| Subreddit 帖子列表 | `reddit_rss.py --subreddit {name}` | `https://www.reddit.com/r/{name}/.rss` | ✅ 已验证 |

**限制**：
- 仅提供有限的帖子，排序由 Reddit 决定
- 可能遇到 429 限流，需稍后重试
- 无评论内容
- 字段有限：标题、作者、链接、发布时间、摘要

## 不可用

| 功能 | 端点 | 状态 | 原因 |
|------|------|------|------|
| 官方 JSON API | `www.reddit.com/*.json` | ❌ 403 | Reddit 阻止未认证请求 |
| 官方搜索 JSON | `www.reddit.com/search.json` | ❌ 403 | 同上 |
| PullPush API | `api.pullpush.io` | ⚠️ 不稳定 | 频繁 429/超时，不作为公开能力 |

## 未测试

- 认证后的 OAuth API（需要用户凭据）
- 其他第三方归档服务

## 探测证据

### 探测时间：2026-10-12

```
Reddit RSS subreddit (Python): 200 OK ✓
Reddit RSS subreddit (rust): 200 OK ✓
Reddit JSON subreddit: 403 Blocked ✗
Reddit search JSON: 403 Blocked ✗
PullPush API: 429 Rate Limited / Timeout ⚠️
```

## 推荐使用

1. **浏览 Subreddit 帖子**：使用 `scripts/reddit_rss.py --subreddit {name}`

## 归档数据说明

PullPush API 提供归档数据，但因频繁 429/超时不稳定，不作为本技能的公开能力。如需归档数据，请直接访问 PullPush 并注意其服务限制。
