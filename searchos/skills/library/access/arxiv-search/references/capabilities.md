# arXiv 能力映射

## 已验证能力

### 论文检索 (`scripts/search.py --query`)

- **功能**: 通过 arXiv API 检索论文元数据
- **路由**: `https://export.arxiv.org/api/query`
- **方法**: HTTP GET
- **参数**:
  - `search_query`: arXiv 查询表达式（必需）
  - `start`: 分页起始位置（默认 0）
  - `max_results`: 返回记录数上限（CLI 映射为 `--limit`，范围 1-100）
- **输出**: JSON 包含 `records` 数组，每条记录含：
  - `source_url`: 论文详情页链接 (如 `https://arxiv.org/abs/2301.12345`)
  - `title`: 标题
  - `authors`: 作者列表
  - `summary`: 摘要
  - `published`: 发布日期 (ISO 8601)
- **CLI 参数**:
  - `--query`: arXiv 查询表达式（必需，与 `--input` 二选一）
  - `--limit`: 返回记录数上限，默认 5，范围 1-100
  - `--timeout`: HTTP 超时秒数，默认 60
  - `--output`: JSON 输出文件路径（可选，默认输出到标准输出）
- **探针证据**: 
  - URL: `https://export.arxiv.org/api/query?search_query=all:%22retrieval%20augmented%20generation%22&start=0&max_results=5`
  - 行为: 返回 Atom XML，包含匹配论文的元数据
- **限制**:
  - 单次最大 100 条结果
  - API 有速率限制，脚本内置重试机制（最多 3 次，间隔递增）
  - 超时默认 60 秒，可通过 `--timeout` 调整

### 离线解析 (`scripts/search.py --input`)

- **功能**: 解析本地 Atom XML 文件，用于无网络环境验证
- **CLI 参数**:
  - `--input`: 离线 Atom XML 文件路径（必需，与 `--query` 二选一）
  - `--output`: JSON 输出文件路径（可选）
- **输出**: JSON 含 `input_mode: "fixture"` 标记
- **限制**: 仅用于接口验证，不适用于真实研究

## 查询语法参考

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

## 未实现能力

- 分页检索（多页遍历）
- 按日期范围过滤
- 按更新时间排序
- 批量 ID 检索
- 全文下载

## 错误处理

- HTTP 400: 查询语法错误，检查 `--query` 参数
- HTTP 429: 限流，自动重试最多 3 次
- HTTP 5xx: 服务端错误，自动重试最多 3 次
- 超时/网络错误: 自动重试最多 3 次，每次间隔递增
- 空结果: 返回空 `records` 数组，不报错