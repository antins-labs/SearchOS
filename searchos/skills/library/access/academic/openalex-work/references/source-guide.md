# OpenAlex API 来源操作说明

本文档描述 OpenAlex Works API 的功能、参数和输出语义。调用以 SKILL.md 中的 CLI 为准。

## API 概述

OpenAlex 是开放的学术图谱 API，提供作品（Works）、作者（Authors）、来源（Sources）、机构（Institutions）、概念（Concepts）、出版商（Publishers）等实体检索。本技能专注于 Works 端点。

**基础 URL**: `https://api.openalex.org/works`

## 检索模式

### 1. 关键词搜索

使用 `query` 参数进行全文搜索：

```bash
python scripts/run.py --query "machine learning" --per-page 10
```

### 2. ID 直接获取

使用 `openalex_id` 参数直接获取单个作品：

```bash
python scripts/run.py --openalex-id "W2626778328"
```

### 3. 过滤检索

使用 `filter` 参数按条件过滤：

```bash
# 按年份过滤
python scripts/run.py --query "deep learning" --filter "publication_year:2024"

# 按类型过滤
python scripts/run.py --query "neural networks" --filter "type:article"

# 组合过滤
python scripts/run.py --query "AI" --filter "publication_year:2024,type:article"
```

### 4. 排序

使用 `sort` 参数排序结果：

```bash
# 按引用量降序
python scripts/run.py --query "transformer" --sort "cited_by_count:desc"

# 按年份降序
python scripts/run.py --query "attention mechanism" --sort "publication_year:desc"
```

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 否* | 搜索查询字符串；与 openalex_id 二选一 |
| `openalex_id` | string | 否* | 作品 ID（W 开头）或完整 URL |
| `per_page` | integer | 否 | 每页结果数，默认 10，范围 1-200 |
| `page` | integer | 否 | 页码，从 1 开始 |
| `filter` | string | 否 | 过滤条件，如 `publication_year:2024` |
| `sort` | string | 否 | 排序方式，如 `cited_by_count:desc` |
| `cursor` | string | 否 | 游标分页令牌 |
| `num_results` | integer | 否 | 限制返回结果数量 |

*注：`query` 和 `openalex_id` 至少提供一个。

## 常用过滤条件

| 过滤器 | 示例 | 说明 |
|--------|------|------|
| `publication_year` | `publication_year:2024` | 出版年份 |
| `type` | `type:article` | 作品类型（article, book, dataset 等） |
| `is_oa` | `is_oa:true` | 开放获取 |
| `cited_by_count` | `cited_by_count:>100` | 引用数范围 |

## 输出字段

每个返回的作品包含：

| 字段 | 说明 |
|------|------|
| `title` | 作品标题 |
| `url` | OpenAlex 作品 URL |
| `publication_year` | 出版年份 |
| `doi` | DOI 链接 |
| `type` | 作品类型 |
| `cited_by_count` | 被引用次数 |
| `openalex_id` | OpenAlex ID（W 开头） |

## 分页说明

- **页码分页**：使用 `page` 参数，适用于小规模结果集
- **游标分页**：使用 `cursor` 参数，适用于大规模结果集

响应中的 `meta` 字段包含分页信息：
- `count`: 总结果数
- `page`: 当前页码
- `per_page`: 每页结果数

## 示例目标 URL

- 搜索：`https://api.openalex.org/works?search=graph+neural+networks&per-page=10`
- 过滤：`https://api.openalex.org/works?search=AI&filter=publication_year:2024`
- 排序：`https://api.openalex.org/works?search=machine+learning&sort=cited_by_count:desc`
- ID 获取：`https://api.openalex.org/works/W2626778328`

## 错误处理

- `http_400`: 参数错误或 URL 格式问题
- `http_404`: 作品不存在（仅 ID 查询）
- `http_429`: 请求频率限制
- `fetch_*`: 网络错误

## 注意事项

1. OpenAlex API 免费使用，无需 API Key（但建议添加 mailto 参数以提高限额）
2. 参数名使用连字符格式（如 `per-page`），CLI 使用下划线（如 `--per-page`）
3. 搜索结果按相关性排序，可通过 `sort` 参数更改