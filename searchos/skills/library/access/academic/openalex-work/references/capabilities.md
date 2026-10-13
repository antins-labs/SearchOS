# OpenAlex Works API 能力映射

本文档记录已验证的 OpenAlex API 能力及其 CLI 映射。

## 已验证能力

### 1. 关键词搜索

**功能**: 按关键词搜索学术作品

**API 端点**: `GET https://api.openalex.org/works?search={query}`

**CLI 命令**:
```bash
python scripts/run.py --query "machine learning" --per-page 10
```

**参数**:
- `search` (API) ← `query` (CLI): 搜索关键词
- `per-page` (API) ← `per_page` (CLI): 每页结果数

**验证证据**:
- URL: `https://api.openalex.org/works?search=machine+learning&per-page=3`
- 响应: HTTP 200，返回包含 `results` 数组和 `meta` 分页信息

**输出字段**: `title`, `url`, `publication_year`, `doi`, `type`, `cited_by_count`, `openalex_id`

---

### 2. ID 直接获取

**功能**: 按 OpenAlex ID 获取单个作品详情

**API 端点**: `GET https://api.openalex.org/works/{id}`

**CLI 命令**:
```bash
python scripts/run.py --openalex-id "W2626778328"
```

**参数**:
- `id` (API) ← `openalex_id` (CLI): OpenAlex 作品 ID（W 开头）

**验证证据**:
- URL: `https://api.openalex.org/works/W2626778328`
- 响应: HTTP 200，返回单个作品对象

**输出**: `result` 对象（非数组）

---

### 3. 过滤检索

**功能**: 按条件过滤搜索结果

**API 端点**: `GET https://api.openalex.org/works?search={query}&filter={filter}`

**CLI 命令**:
```bash
python scripts/run.py --query "AI" --filter "publication_year:2024"
```

**参数**:
- `filter` (API) ← `filter` (CLI): 过滤条件

**已验证过滤条件**:
- `publication_year:2024` - 按年份过滤
- `type:article` - 按类型过滤
- 组合条件: `publication_year:2024,type:article`

**验证证据**:
- URL: `https://api.openalex.org/works?search=transformer&filter=publication_year%3A2024`
- 响应: HTTP 200，返回过滤后结果

---

### 4. 排序

**功能**: 按指定字段排序结果

**API 端点**: `GET https://api.openalex.org/works?search={query}&sort={sort}`

**CLI 命令**:
```bash
python scripts/run.py --query "transformer" --sort "cited_by_count:desc"
```

**参数**:
- `sort` (API) ← `sort` (CLI): 排序方式

**已验证排序**:
- `cited_by_count:desc` - 按引用量降序
- `publication_year:desc` - 按年份降序

**验证证据**:
- URL: `https://api.openalex.org/works?search=transformer&sort=cited_by_count%3Adesc`
- 响应: HTTP 200，结果按指定顺序排列

---

### 5. 分页

**功能**: 获取指定页码的结果

**API 端点**: `GET https://api.openalex.org/works?search={query}&page={page}`

**CLI 命令**:
```bash
python scripts/run.py --query "neural networks" --page 2 --per-page 10
```

**参数**:
- `page` (API) ← `page` (CLI): 页码（从 1 开始）

**验证证据**:
- URL: `https://api.openalex.org/works?search=neural+networks&page=2`
- 响应: HTTP 200，`meta.page` 返回当前页码

---

## 未实现能力

以下能力在 API 中存在但未在当前 CLI 中实现：

| 能力 | API 参数 | 状态 |
|------|----------|------|
| 游标分页 | `cursor` | 参数已定义，未验证 |
| 邮箱联系 | `mailto` | 未实现（可提高请求限额） |
| 选择字段 | `select` | 未实现 |
| 分组聚合 | `group_by` | 未实现 |
| 搜索字段 | `search` 支持多字段 | 未实现 |

---

## 错误处理

| 错误类型 | 原因 | CLI 行为 |
|----------|------|----------|
| `http_400` | 参数错误 | 返回错误 JSON，退出码 1 |
| `http_404` | 作品不存在（ID 查询） | 返回错误 JSON，退出码 1 |
| `http_429` | 请求频率限制 | 返回错误 JSON，退出码 1 |
| `fetch_*` | 网络错误 | 返回错误 JSON，退出码 1 |
| `json_decode` | 响应解析失败 | 返回错误 JSON，退出码 1 |

---

## 已知限制

1. **无认证**: 当前未使用 `mailto` 参数，请求限额较低
2. **字段选择**: 返回固定字段集，不支持自定义
3. **游标分页**: 参数已定义但未完整验证
4. **空结果**: 搜索无匹配时返回空数组，退出码 0

---

## 参数映射表

| CLI 参数 | API 参数 | 说明 |
|----------|----------|------|
| `--query` | `search` | 搜索关键词 |
| `--openalex-id` | URL 路径 | 作品 ID |
| `--per-page` | `per-page` | 每页结果数 |
| `--page` | `page` | 页码 |
| `--filter` | `filter` | 过滤条件 |
| `--sort` | `sort` | 排序方式 |
| `--cursor` | `cursor` | 游标令牌 |
| `--num-results` | 无 | 本地截断 |

---

## 验证日期

- 2026-10-13: 所有已验证能力通过实际 API 调用测试