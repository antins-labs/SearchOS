# 来源操作说明

此技能通过 Reddit 官方 RSS 订阅读取公开板块帖子列表。

## 功能

### reddit_rss.py - 读取板块帖子

```bash
python scripts/reddit_rss.py --subreddit Python --limit 25 --output result.json
```

**参数**：
- `--subreddit, -s`：板块名称（必填），可带或不带 `r/` 前缀
- `--limit, -l`：返回数量，1-100（默认 25）
- `--output, -o`：输出文件路径（默认 stdout）

**输出字段**：
- `id`：帖子 ID
- `title`：标题
- `author`：作者用户名
- `subreddit`：板块名称
- `url`/`source_url`：帖子链接
- `published`：发布时间（ISO 8601）
- `updated`：更新时间
- `content`/`summary`：内容或摘要

**限制**：
- RSS 仅提供有限的最近帖子，排序由 Reddit 决定
- 无评论内容
- 板块名必须为 2-21 位字母数字下划线

## 旧版说明

旧版 `scripts/run.py` 和 `scripts/source.py` 依赖 PullPush API，该服务不稳定，已不推荐使用。