---
name: arxiv-search
description: 检索 arXiv 论文，获取标题、作者、摘要及原始来源链接；适用于学术文献发现与论文元数据获取。
compatibility: Python 3.10+；仅使用标准库，联网检索需要访问 export.arxiv.org。
metadata:
  searchos-category: access
  host: arxiv.org
---

# arXiv 论文检索

使用技能目录中的 `scripts/search.py`。命令中的脚本路径相对本技能目录解析，输出路径传入当前任务的可写目录。脚本不依赖宿主框架或专有环境变量。

## 命令概览

| 命令 | 用途 |
|------|------|
| `--query` | 在线检索 arXiv 论文 |
| `--input` | 离线解析 Atom XML（仅用于验证） |

## 在线检索

```bash
python scripts/search.py --query 'all:"retrieval augmented generation"' --limit 5 --output papers.json
```

### 参数说明

| 参数 | 必需 | 说明 |
|------|------|------|
| `--query` | 与 `--input` 二选一 | arXiv 查询表达式 |
| `--limit` | 否 | 返回记录数上限，范围 1-100，默认 5 |
| `--timeout` | 否 | HTTP 超时秒数，默认 60 |
| `--output` | 否 | JSON 输出文件路径；未指定时输出到标准输出 |

### 查询语法

arXiv 支持多种查询前缀：

| 前缀 | 含义 | 示例 |
|------|------|------|
| `ti:` | 标题 | `ti:"machine learning"` |
| `au:` | 作者 | `au:Bengio` |
| `abs:` | 摘要 | `abs:"neural network"` |
| `cat:` | 分类 | `cat:cs.AI` |
| `all:` | 所有字段 | `all:"large language models"` |
| `id:` | arXiv ID | `id:2301.12345` |

组合查询示例：
- `ti:"transformer" AND cat:cs.CL`
- `au:LeCun OR au:Bengio`
- `all:"retrieval augmented generation" AND cat:cs.AI`

### 输出格式

返回 JSON 包含以下字段：

```json
{
  "input_mode": "live",
  "request_url": "https://export.arxiv.org/api/query?...",
  "retrieved_at": "2026-10-13T09:30:26.546807+00:00",
  "records": [
    {
      "source_url": "https://arxiv.org/abs/2411.18583v1",
      "title": "论文标题",
      "authors": ["作者1", "作者2"],
      "summary": "摘要内容",
      "published": "2024-11-27T18:27:07Z"
    }
  ],
  "sources": [{"url": "...", "content": "原始 Atom XML"}]
}
```

## 离线解析

```bash
python scripts/search.py --input references/example.atom --output sample.json
```

用于无网络环境验证解析逻辑。输出含 `input_mode: "fixture"` 标记，不得用作研究证据。

## 错误处理

- **HTTP 400**: 查询语法错误，检查 `--query` 参数
- **HTTP 429**: 限流，自动重试最多 3 次
- **HTTP 5xx**: 服务端错误，自动重试最多 3 次
- **超时/网络错误**: 自动重试最多 3 次，每次间隔递增
- **空结果**: 返回空 `records` 数组，不报错

## 限制

- 单次最大 100 条结果
- API 有速率限制，建议避免高频并发请求
- 摘要仅供参考，涉及全文结论时需访问论文来源
- 无命中返回空数组，不代表完整文献集合

## 详细文档

- [能力映射](references/capabilities.md)：已验证能力、API 参数、限制说明