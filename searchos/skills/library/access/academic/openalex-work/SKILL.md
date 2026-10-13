---
name: openalex-work
description: 从 api.openalex.org 抽取学术作品：标题、URL、出版年份、DOI、类型。支持关键词搜索、ID 直接获取、过滤和排序。
metadata:
  searchos-category: access
  searchos-aliases: openalex_work
  host: api.openalex.org
compatibility: Python 3.10+；依赖见 requirements.txt；检索需要网络。
---

# openalex-work

从 OpenAlex API (api.openalex.org) 抽取学术作品信息，包括标题、URL、出版年份、DOI、类型等字段。

## 能力概览

| 命令 | 用途 | 示例 |
|------|------|------|
| 搜索作品 | 按关键词检索学术作品 | `--query "machine learning"` |
| 获取作品 | 按 ID 直接获取作品详情 | `--openalex-id "W2626778328"` |
| 过滤检索 | 按年份、类型等条件过滤 | `--query "AI" --filter "publication_year:2024"` |
| 排序结果 | 按引用量、年份排序 | `--query "transformer" --sort "cited_by_count:desc"` |

## 调用方式

脚本路径相对技能目录，输出路径相对调用者当前工作目录。

```bash
# 显示帮助
python scripts/run.py --help

# 搜索作品
python scripts/run.py --query "graph neural networks" --per-page 10

# 按 ID 获取
python scripts/run.py --openalex-id "W2626778328" --result-file work.json

# 过滤 + 排序
python scripts/run.py --query "deep learning" --filter "publication_year:2024" --sort "cited_by_count:desc"

# 使用 JSON 参数文件
python scripts/run.py --params-file params.json --result-file results.json

# 从 stdin 读取参数
echo '{"query": "attention mechanism", "per_page": 5}' | python scripts/run.py --params-file -
```

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `--query` | string | 否* | 搜索查询字符串 |
| `--openalex-id` | string | 否* | OpenAlex 作品 ID（W 开头）或完整 URL |
| `--per-page` | integer | 否 | 每页结果数（1-200），默认 10 |
| `--page` | integer | 否 | 页码，从 1 开始 |
| `--filter` | string | 否 | 过滤条件，如 `publication_year:2024,type:article` |
| `--sort` | string | 否 | 排序方式，如 `cited_by_count:desc` |
| `--num-results` | integer | 否 | 限制返回结果数量 |
| `--params` | string | 否 | JSON 格式参数对象 |
| `--params-file` | string | 否 | JSON 参数文件路径；`-` 表示 stdin |
| `--result-file` | string | 否 | 输出 JSON 文件路径；默认 stdout |
| `--validate-only` | flag | 否 | 仅校验参数，不执行检索 |
| `--check-dependencies` | flag | 否 | 检查 Python 依赖 |

*`--query` 和 `--openalex-id` 至少提供一个。

## 输出格式

### 搜索结果

```json
{
  "results": [
    {
      "title": "Attention Is All You Need",
      "url": "https://openalex.org/W2626778328",
      "publication_year": 2017,
      "doi": "https://doi.org/10.48550/arXiv.1706.03762",
      "type": "article",
      "cited_by_count": 50000,
      "openalex_id": "W2626778328"
    }
  ],
  "count": 1,
  "total": 1000000,
  "page": 1,
  "per_page": 10,
  "source": "https://api.openalex.org/works?search=..."
}
```

### 单作品获取

```json
{
  "result": {
    "title": "Attention Is All You Need",
    "url": "https://openalex.org/W2626778328",
    "publication_year": 2017,
    "doi": "https://doi.org/10.48550/arXiv.1706.03762",
    "type": "article",
    "cited_by_count": 50000,
    "openalex_id": "W2626778328"
  },
  "source": "https://api.openalex.org/works/W2626778328"
}
```

## 环境与依赖

```bash
python -m pip install -r requirements.txt
```

依赖：`aiohttp`

## 错误处理

- 非零退出码表示错误
- 错误信息输出到 stderr
- `error` 字段包含错误类型：`http_400`、`http_404`、`fetch_*` 等

## 常用过滤条件

| 过滤器 | 示例 | 说明 |
|--------|------|------|
| `publication_year` | `publication_year:2024` | 出版年份 |
| `type` | `type:article` | 作品类型 |
| `is_oa` | `is_oa:true` | 开放获取 |
| `cited_by_count` | `cited_by_count:>100` | 引用数范围 |

详细说明见 [来源操作说明](references/source-guide.md)。

## 来源归属

所有结果包含 `source` 字段，指向原始 OpenAlex API URL。数据来源：OpenAlex（https://openalex.org），开放学术图谱。