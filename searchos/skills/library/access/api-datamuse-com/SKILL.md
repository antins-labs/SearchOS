---
name: api-datamuse-com
description: 通用词语检索技能，基于 Datamuse API 提供同义词、相关词、反义词、形容词关联等多种词语关系查询。
metadata:
  searchos-category: access
  host: api.datamuse.com
---

# api-datamuse-com

## 概述

本技能通过 Datamuse 公开 API（`https://api.datamuse.com`）提供词语关系检索功能。支持查询同义词、相关词、反义词、描述词等多种语义关系，返回包含词语、相关性分数及来源 URL 的 JSON 记录。

## 命令

### query

检索与指定词语相关的词语。

```bash
python scripts/query.py --query <词语> [--relation <关系类型>] [--limit <数量>] [--output <文件路径>]
```

**参数说明：**

- `--query` / `-q`：必填，目标查询词语。
- `--relation` / `-r`：可选，关系类型，默认为 `ml`（相关词）。可选值：
  - `ml`：相关词（means like，语义相似）
  - `syn`：同义词
  - `ant`：反义词
  - `jja`：被指定形容词修饰的名词（如 `big` → `man`, `deal`）
  - `jjb`：修饰指定名词的形容词（如 `ocean` → `open`, `vast`）
  - `sl`：发音相似词
  - `sp`：拼写相似词（支持通配符 `?` 和 `*`）
  - `trg`：触发相关词（统计共现）
- `--limit` / `-l`：可选，返回结果数量上限，默认 10，最大 100。
- `--output` / `-o`：可选，输出 JSON 文件路径。若不指定则输出到 stdout。
- `--help` / `-h`：显示帮助信息。

**输出格式：**

JSON 对象，包含 `records` 数组，每条记录包含：

```json
{
  "records": [
    {
      "word": "inquiry",
      "score": 43044,
      "source_url": "https://api.datamuse.com/words?ml=research&max=10"
    }
  ],
  "query": "research",
  "relation": "ml",
  "total": 1
}
```

字段说明：
- `word`：返回的词语。
- `score`：排序分数，数值用于结果排序，不代表统一的相关性度量尺度。
- `source_url`：原始请求 URL，用于溯源。
- `query`：原始查询词。
- `relation`：使用的关系类型。
- `total`：返回记录总数。

## 依赖

- Python 3.6+（使用标准库 `urllib.request`、`json`、`argparse`，无第三方依赖）

## 使用示例

```bash
# 查询 research 的相关词
python scripts/query.py --query research --limit 5

# 查询 good 的同义词
python scripts/query.py --query good --relation syn --limit 10

# 查询 ocean 的常用形容词
python scripts/query.py --query ocean --relation jjb --limit 5

# 查询 big 常修饰的名词
python scripts/query.py --query big --relation jja --limit 5

# 输出到文件
python scripts/query.py --query happy --relation syn --output results.json
```

## 错误处理

- 网络请求失败时，脚本返回非零退出码并输出错误信息到 stderr。
- HTTP 非 200 响应码视为请求失败。
- 空结果返回空 `records` 数组，退出码为 0。

## 数据来源

所有数据来自 Datamuse 公开 API：
- API 文档：https://www.datamuse.com/api/
- API 端点：https://api.datamuse.com/words

## 注意事项

- 当前 API 无需认证即可使用，实测通过；但官网计划于 2027 年引入认证机制，具体以官网公告为准。
- 建议控制请求频率以避免限流。
- 返回的 `score` 字段仅用于排序，不应解释为具有统一尺度的相关性度量。
- 拼写相似查询（`sp`）支持通配符：`?` 匹配单个字符，`*` 匹配任意字符序列。
