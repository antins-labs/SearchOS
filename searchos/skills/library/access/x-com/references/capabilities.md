# X/Twitter 公开访问能力说明

## 探测日期

2026-10-12

## 已验证能力

### 1. 帖子详情获取 (oEmbed)

**接口**: `https://publish.twitter.com/oembed`

**验证结果**: ✓ 可用

**工作原理**:
- 官方公开接口，无需认证
- URL 参数: `url=https://twitter.com/{username}/status/{tweet_id}&omit_script=true`
- **重要**: URL 中的用户名被忽略，仅帖子 ID 生效
- 返回 JSON，包含 HTML 片段，需解析提取文本

**可获取字段**:
- `author_name`: 作者显示名称
- `author_url`: 作者主页链接 (可提取用户名)
- `url`: 帖子永久链接 (用于验证 ID)
- `html`: 包含帖子文本的 blockquote

**不可获取**:
- 点赞数、转发数、回复数
- 图片、视频、链接卡片
- 精确时间戳 (仅 HTML 中有日期文本)
- 帖子是否为回复

**限制**:
- 仅公开帖子可获取
- 被保护账户的帖子返回 404
- 不存在的帖子返回 404

**探测样例**:
| 帖子 ID | 作者 | 文本 | 状态 |
|---------|------|------|------|
| 20 | jack | just setting up my twttr | ✓ |
| 21 | Biz Stone | just setting up my twttr | ✓ |
| 22 | noah glass | just setting up my twttr | ✓ |
| 40 | Biz Stone | wishing I had another sammich | ✓ |
| 9999999999999999999 | - | - | ✗ 404 |

### 2. 用户资料获取 (HTML HEAD 元数据)

**接口**: `https://x.com/{username}` HTML 页面 HEAD 部分

**验证结果**: ✓ 可用

**工作原理**:
- 从 HTML `<head>` 中的 `<meta>` 标签提取 Open Graph 和 Twitter Card 元数据
- 仅读取前 128KB，遇到 `</head>` 即停止
- 无需认证，公开页面

**可获取字段**:
- `og:title`: 格式为 "Display Name (@username) on X"
- `og:description`: 个人简介
- `og:image`: 头像 URL
- `og:url`: 用户主页链接
- `twitter:label1` + `twitter:data1`: 通常是 "Posts" + 发帖数（原始文本如 "31K"）
- `twitter:label2` + `twitter:data2`: 通常是 "Joined" + 加入时间

**不可获取**:
- 关注者数、关注数
- 用户 ID
- 认证状态
- 封面图

**探测样例**:
| 用户名 | 显示名称 | 状态 |
|--------|----------|------|
| jack | jack (@jack) | ✓ |
| NASA | NASA (@NASA) | ✓ |
| nonexistentuserxyz123456 | - | ✗ 404 或无元数据 |

## 未验证/未实现能力

### 搜索

**状态**: ✗ 未实现

**说明**: 
- 访问 `https://x.com/search?q=...` 需要登录
- 公开 oEmbed 接口不支持搜索
- 官方 API 需要 bearer token
- 本技能未实现搜索功能，不声称平台没有搜索 API

### 用户时间线

**状态**: ✗ 未实现

**说明**:
- 用户主页 HTML 不包含帖子列表，仅元数据
- 获取用户推文列表需要登录或 API 凭据
- 本技能未实现时间线功能

### 高级搜索

**状态**: ✗ 未实现

### API 接口

**状态**: ✗ 未实现

- `api.twitter.com/2/*` 需要 bearer token
- 本技能未使用官方 API

## 技术说明

### oEmbed ID 验证

由于 oEmbed 忽略 URL 中的用户名，必须验证返回的 `url` 字段中的帖子 ID 与请求一致：

```python
if not url.endswith(f'/{tweet_id}'):
    return None  # ID 不匹配
```

### 作者验证

从返回的 `url` 字段提取作者用户名，不信任输入路径：

```python
username = extract_username_from_url(data['url'])
```

### HTML HEAD 解析

用户资料脚本仅读取 HTML HEAD 部分：

```python
# 分块读取，遇到 </head> 立即停止
while total_read < MAX_HEAD_SIZE:
    chunk = response.read1(4096)
    if not chunk:
        break
    html_buffer.write(chunk)
    total_read += len(chunk)
    if b'</head>' in html_buffer.getvalue().lower():
        break
```

### HTML 实体处理

使用 `html.unescape` 和 `HTMLParser` 处理 HTML 实体，保留 `<br>` 换行：

```python
from html import unescape
text = unescape(raw_text)
```

### URL 验证

使用 `urlsplit` 严格验证 x.com/twitter.com 主机：

```python
from urllib.parse import urlsplit
parsed = urlsplit(url)
if parsed.netloc not in ('x.com', 'twitter.com', 'www.x.com', 'www.twitter.com'):
    raise ValueError('Invalid host')
```

### ID 验证

帖子 ID 必须为正整数：

```python
if not tweet_id.isdigit() or int(tweet_id) <= 0:
    raise ValueError('Invalid tweet ID')
```

## 已知问题

1. **oEmbed 速率限制**: 未观察到明确限制，但大量请求可能被限速
2. **用户资料解析**: 元标签格式可能变化，需定期验证
3. **中文内容**: oEmbed 返回的 HTML 中中文正常显示