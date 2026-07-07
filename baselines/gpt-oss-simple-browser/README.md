# Search Agent Baseline

基于 GPT-OSS SimpleBrowser 改造的 ReAct 搜索智能体基线系统。通过 **思考 → 工具调用 → 观察 → ... → 回答** 的循环模式，自主完成网页搜索、页面浏览和信息提取任务。

## 快速开始

### 环境要求

- Python 3.10+
- 依赖：`aiohttp`, `openai`, `anthropic`, `lxml`, `html2text`, `certifi`

### 配置 API Key

```bash
# OpenAI 兼容接口（DeepSeek、GLM 等）
export OPENAI_API_KEY="your-key"

# 或 Anthropic Claude
export ANTHROPIC_API_KEY="your-key"
```

### 单条查询

```bash
python -m baselines.gpt-oss-simple-browser query "姚鑫浩发表了哪些论文" -v --max-iterations 20
```

### 批量推理

```bash
python -m baselines.gpt-oss-simple-browser batch data/dataset.jsonl \
    -c 5 \
    -o outputs/predictions.jsonl \
    --provider openai \
    --model DeepSeek-V3.1
```

## CLI 参数

### 子命令

| 子命令 | 说明 |
|--------|------|
| `query <问题>` | 单条查询模式 |
| `batch <输入文件>` | 批量推理模式 |

> 为保持向后兼容，直接传入问题文本（不指定子命令）等价于 `query`。

### 通用参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--provider` | `openai` | LLM 提供商：`openai` 或 `claude` |
| `--model` | 自动选择 | 模型名称（openai 默认 DeepSeek-V3.1，claude 默认 claude-sonnet-4-20250514） |
| `--max-iterations` | `15` | Agent 最大循环轮数 |
| `--view-tokens` | `2048` | 页面显示窗口的 token 预算 |
| `--search-page-size` | `10` | 单次搜索返回结果数 |
| `-v, --verbose` | 关闭 | 显示中间推理过程和工具调用详情 |
| `--debug` | 关闭 | 启用 DEBUG 级别日志 |
| `--save-dir` | 无 | 保存完整对话记录的目录 |

### 批量推理专用参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-o, --output` | `<输入文件>_predictions.jsonl` | 输出文件路径 |
| `-c, --concurrency` | `5` | 并发任务数 |
| `--query-field` | 自动检测 | 输入数据中的问题字段名 |
| `--id-field` | 自动检测 | 输入数据中的唯一 ID 字段名 |
| `--limit` | 无 | 仅处理前 N 条数据 |
| `--overwrite` | 关闭 | 覆盖已有输出（禁用断点续跑） |

## 架构

```
search_agent/
├── main.py              # CLI 入口，参数解析
├── agent.py             # 核心 Agent 循环（ReAct loop）
├── state.py             # 浏览器状态管理（页面栈、滚动、页内查找）
├── batch.py             # 批量推理引擎（并发控制、断点续跑）
├── config.py            # AgentConfig 配置
├── models.py            # 数据模型（PageContents, SearchResult, Extract）
├── llm/
│   ├── base.py          # LLM 抽象接口（BaseLLM, LLMResponse, ToolCall）
│   ├── openai_llm.py    # OpenAI 兼容实现（支持 DeepSeek、GLM 等）
│   └── claude_llm.py    # Anthropic Claude 实现
└── tools/
    ├── tool_defs.py     # 工具定义（OpenAI / Claude 双格式）
    ├── search.py        # 搜索工具（调用内部 RAG API）
    ├── browser.py       # 页面抓取（Chrome UA 伪装、重试逻辑）
    └── html_processor.py # HTML → 纯文本转换（GPT-OSS 链接格式）
```

### Agent 工具集

Agent 拥有三个工具：

| 工具 | 功能 |
|------|------|
| `web_search(query)` | 调用内部 RAG API 进行网页搜索 |
| `open_page(id, loc)` | 通过链接 ID 或 URL 打开页面，支持按行号滚动 |
| `find_in_page(pattern)` | 在当前页面中进行大小写不敏感的文本搜索 |

### 关键设计

- **双 LLM 适配层**：同时支持 OpenAI 兼容接口和 Claude 原生接口，消息格式和工具定义自动切换
- **浏览器状态栈**：维护页面访问历史，支持页面缓存、行号显示和 token 预算控制的滚动窗口
- **HTML 链接格式**：页面中的链接被转换为 `【id†文本†域名】` 格式（源自 GPT-OSS），LLM 通过 ID 引用链接
- **搜索结果缓存**：搜索 API 返回的页面内容会被缓存，`open_page` 时优先使用缓存避免重复抓取
- **批量断点续跑**：输出文件同时作为 checkpoint，重启后自动跳过已完成的条目

## 输入数据格式

批量推理输入为 JSONL 格式，每行一个 JSON 对象。系统会自动检测以下字段：

- **查询字段**：`question` > `query` > `input` > `prompt`（优先级从高到低）
- **ID 字段**：`instance_id` > `id` > `task_id` > `question_id`

示例：

```json
{"id": "q001", "question": "量子计算的基本原理是什么？"}
{"id": "q002", "question": "2024年诺贝尔物理学奖颁给了谁？"}
```

## 输出格式

### 单条查询（`--save-dir`）

保存为 `result_<timestamp>.json`，包含：

```json
{
  "query": "原始问题",
  "answer": "最终回答",
  "system_prompt": "系统提示词",
  "tools": [],
  "messages": [],
  "metadata": {
    "model": "模型名称",
    "provider": "提供商",
    "tool_rounds": 5,
    "usage": {"input_tokens": 0, "output_tokens": 0}
  }
}
```

### 批量推理

输出为 JSONL，每行在原始数据基础上追加 `prediction` 字段：

```json
{"id": "q001", "question": "...", "prediction": "Agent 的回答"}
```

## 注意事项

- 搜索功能依赖内部 RAG API（通过 `RAGFLOW_ENDPOINT` 环境变量配置），需在内网环境使用
- OpenAI 兼容模式通过 `AsyncOpenAI` 客户端实现，适用于所有兼容 OpenAI API 格式的模型服务
- 页面抓取使用 Chrome 浏览器 UA 伪装，对 403/429/5xx 状态码自动重试（最多 2 次）
