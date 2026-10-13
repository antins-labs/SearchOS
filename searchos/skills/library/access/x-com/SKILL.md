---
name: x-com
description: 读取 X/Twitter 公开帖子与用户资料。支持通过帖子 ID 获取公开帖子详情（使用官方 oEmbed 接口），以及通过用户名获取公开用户资料（从 HTML 页面 HEAD 元数据提取）。搜索功能需要登录，不支持无凭据公开检索。
metadata:
  searchos-category: access
  host: x.com
---

# X/Twitter 公开内容读取技能

## 能力概述

| 功能 | 状态 | 说明 |
|------|------|------|
| 帖子详情 | ✓ 可用 | 通过 oEmbed 接口获取公开帖子文本、作者、链接 |
| 用户资料 | ✓ 可用 | 从用户主页 HTML HEAD 提取公开元数据 |
| 搜索 | ✗ 未实现 | 需要登录，本技能未实现无凭据公开检索 |
| 时间线 | ✗ 未实现 | 需要登录或 API 凭据 |
| 用户推文列表 | ✗ 未实现 | 需要登录 |

详细能力说明见 [references/capabilities.md](references/capabilities.md)。

## 命令指南

### 获取帖子详情

```bash
python scripts/get_tweet.py --id <帖子ID>
python scripts/get_tweet.py --url "https://x.com/用户名/status/帖子ID"
```

- 通过官方 `publish.twitter.com/oembed` 接口获取公开帖子
- 返回帖子文本、作者用户名、帖子链接
- **注意**：oEmbed 忽略 URL 中的用户名，仅根据帖子 ID 查询；脚本会验证返回的作者信息与帖子 ID 一致

**输出字段**：
- `id`: 帖子 ID
- `author_name`: 作者显示名称
- `author_username`: 作者用户名（从返回的 URL 解析）
- `text`: 帖子文本内容
- `url`: 帖子永久链接
- `source_url`: oEmbed API 来源 URL

### 获取用户资料

```bash
python scripts/get_user.py --username <用户名>
```

- 从 `x.com/{username}` 页面 HEAD 部分提取公开元数据
- 仅读取前 128KB，遇到 `</head>` 即停止
- 返回显示名称、简介、头像、发帖数、加入时间等

**输出字段**：
- `username`: 用户名
- `display_name`: 显示名称
- `description`: 个人简介
- `profile_image_url`: 头像 URL
- `posts_count`: 发帖数（原始文本，如 "31K"）
- `joined`: 加入时间（如可解析）
- `url`: 用户主页链接
- `source_url`: 数据来源 URL

### 批量获取帖子

```bash
python scripts/get_tweets.py --ids ID1,ID2,ID3
python scripts/get_tweets.py --file ids.txt
```

- 批量获取多个帖子详情
- 每个帖子独立请求，失败记录在 `errors` 数组
- 部分失败时返回成功记录但退出码为非零

**输出结构**：
- `records`: 成功获取的帖子数组
- `summary.found`: 成功数量
- `summary.not_found`: 失败数量
- `summary.errors`: 失败 ID 及错误信息数组

## 使用限制

1. **帖子可见性**：仅限公开帖子。被保护/私密账户的帖子无法获取。
2. **oEmbed 限制**：
   - 仅返回帖子文本，不含图片/视频/链接卡片等富媒体
   - 不含点赞数、转发数、回复数等互动数据
   - 不含精确时间戳（仅 HTML 中的日期文本）
3. **用户资料限制**：
   - 仅从 HTML HEAD 元标签提取，不含关注者/关注数
   - `posts_count` 为原始文本（如 "31K"），非精确数值
   - 部分字段可能缺失（如未设置简介）
4. **搜索/时间线**：需要登录凭据，本技能未实现

## 错误处理

- 帖子不存在或非公开：返回空 `records` 数组，退出码 1
- 用户不存在：返回空 `records` 数组，退出码 1
- 网络错误：输出错误信息到 stderr，退出码非零
- 批量命令部分失败：返回成功记录，`errors` 数组记录失败项，退出码 1

## 数据来源

- 帖子：`https://publish.twitter.com/oembed`（官方公开接口）
- 用户：`https://x.com/{username}` HTML 页面 HEAD 元数据

## 依赖

- Python 3.9+（使用标准库 urllib、json、re、argparse、html）
- 无需额外安装依赖

## 示例

获取 Jack 的第一条推文：
```bash
python scripts/get_tweet.py --id 20
```

获取 NASA 用户资料：
```bash
python scripts/get_user.py --username NASA
```

批量获取多个帖子：
```bash
python scripts/get_tweets.py --ids 20,21,22,40
```