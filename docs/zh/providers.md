# 模型 Provider 配置指南

[English](../providers.md) | **简体中文**

SearchOS 的 11 个模型角色（orchestrator、extraction、judge…）统一经 `searchos/config/models.py:get_model_for(role)` 构造，底层是 LangChain 的 `ChatOpenAI` / `ChatAnthropic`。

**最快方式：首次运行 `python -m searchos` 会自动进入命令行配置向导**（选厂商 → 填 key → 写入 `.env`），或随时 `python -m searchos --setup` 重新配置。手动配置只需两行环境变量：

```bash
# .env（参考根目录 .env.example）
SF_PROVIDER=zhipu-coding
ZHIPU_API_KEY=xxx
```

`SF_PROVIDER` 会为全部角色生成默认的 profile 绑定（分五档：`main` / `judge` / `fast` / `synthesis` / `reformat`），任何字段仍可用 `SF_PROFILES__*` / `SF_ROLES__*` 精细覆写（深合并，不会丢其余默认值）。

## 预设总览

### Coding Plan（Anthropic 协议，按月订阅）

各厂商为 Claude Code 提供的 Anthropic 兼容端点，SearchOS 直接复用（走 `ChatAnthropic` + 自定义 `base_url`）：

| `SF_PROVIDER` | 厂商 | 端点 | Key 环境变量 | 默认模型 |
|---|---|---|---|---|
| `zhipu-coding` | 智谱 GLM Coding Plan（中国站） | `open.bigmodel.cn/api/anthropic` | `ZHIPU_API_KEY` | glm-5.2 / glm-4.7 |
| `zai-coding` | Z.ai GLM Coding Plan（国际站） | `api.z.ai/api/anthropic` | `ZAI_API_KEY` | glm-5.2 / glm-4.7 |
| `kimi-coding` | Kimi For Coding 订阅 | `api.kimi.com/coding` | `KIMI_API_KEY` | kimi-for-coding |
| `moonshot-anthropic` | Moonshot 开放平台（按量） | `api.moonshot.cn/anthropic` | `MOONSHOT_API_KEY` | kimi-k2.5 |
| `minimax-coding` | MiniMax Coding Plan | `api.minimaxi.com/anthropic` | `MINIMAX_API_KEY` | MiniMax-M3 |
| `qwen-coding` | 阿里百炼编程套餐 | `coding.dashscope.aliyuncs.com/apps/anthropic` | `DASHSCOPE_API_KEY` | qwen3.7-plus |
| `volcengine-coding` | 火山方舟 Coding Plan | `ark.cn-beijing.volces.com/api/coding` | `ARK_API_KEY` | doubao-seed-code-preview-latest |
| `deepseek-anthropic` | DeepSeek（按量，无套餐） | `api.deepseek.com/anthropic` | `DEEPSEEK_API_KEY` | deepseek-v4-flash |
| `anthropic` | Anthropic 官方 | `api.anthropic.com` | `ANTHROPIC_API_KEY` | claude-sonnet-5 / claude-haiku-4-5 |

注意事项：

- **Key 专属性**：Kimi 订阅 Key 在 kimi.com/code/console 创建，与开放平台不通用；阿里编程套餐 Key 为 `sk-sp-` 前缀专属；智谱团队版 Coding Key 与平台其它 Key 不通用；MiniMax 订阅 Key 与按量 Key 分开。
- **条款限制**：阿里编程套餐条款仅授权「编程工具交互式使用」，智谱 Coding Plan 也限官方支持的编程工具——把套餐 Key 用于 agent 框架前请自行确认条款；按量 Key 无此限制。
- **Claude 订阅不可用**：Claude Pro/Max 的 OAuth token（`claude setup-token` 产物）按 Anthropic ToS 仅限 Claude Code / claude.ai 使用，`anthropic` 预设只支持 Console API key。
- **Anthropic 官方新模型**（Opus 4.7+ / Sonnet 5）已移除 `temperature` 参数，预设自动省略；其它厂商的 Anthropic 兼容端点不受影响。

### 按量 API（OpenAI 协议）

| `SF_PROVIDER` | 厂商 | 端点 | Key 环境变量 | 默认模型 |
|---|---|---|---|---|
| `deepseek` | DeepSeek | `api.deepseek.com` | `DEEPSEEK_API_KEY` | deepseek-v4-flash |
| `zhipu` | 智谱按量（中国站） | `open.bigmodel.cn/api/paas/v4` | `ZHIPU_API_KEY` | glm-5.2 / glm-4.7-flash |
| `zai` | Z.ai 按量（国际站） | `api.z.ai/api/paas/v4` | `ZAI_API_KEY` | glm-5.2 / glm-4.7-flash |
| `moonshot`（别名 `kimi`） | Moonshot 开放平台 | `api.moonshot.cn/v1` | `MOONSHOT_API_KEY` | kimi-k2.5 |
| `minimax` | MiniMax | `api.minimaxi.com/v1` | `MINIMAX_API_KEY` | MiniMax-M3 |
| `dashscope`（别名 `qwen`） | 阿里百炼 | `dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` | qwen3.7-plus |
| `volcengine`（别名 `doubao`/`ark`） | 火山方舟 | `ark.cn-beijing.volces.com/api/v3` | `ARK_API_KEY` | doubao-seed-2.0-pro |
| `openai` | OpenAI 官方 | `api.openai.com/v1` | `OPENAI_API_KEY` | gpt-5.5 |
| `openrouter` | OpenRouter 聚合 | `openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | anthropic/claude-sonnet-4.5 |
| `siliconflow` | 硅基流动（中国站） | `api.siliconflow.cn/v1` | `SILICONFLOW_API_KEY` | deepseek-ai/DeepSeek-V3.2 |
| `gemini` | Google Gemini 兼容层 | `generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` | gemini-3.5-flash |
| `xai` | xAI Grok | `api.x.ai/v1` | `XAI_API_KEY` | grok-4.3 |

注意事项：

- **DeepSeek** 输出上限 8192 tokens，`reformat` 档已自动钳制；超大表格导出建议换大输出窗口的厂商。旧模型名 `deepseek-chat` / `deepseek-reasoner` 已弃用，映射到 v4-flash。
- **OpenAI GPT-5 系**为推理模型，不接受 `temperature`，预设自动省略。
- **国际站切换**：MiniMax / Moonshot / 阿里 / 硅基流动的国际站域名用 `SF_API_BASE` 覆盖即可（见 `.env.example`；硅基流动中国站与国际站账号不互通）。
- **火山方舟**模型 id 以控制台为准，必要时 `SF_MODEL` 覆盖。

### 本地部署

```bash
SF_PROVIDER=ollama
SF_MODEL=qwen3:32b          # 必填

SF_PROVIDER=vllm
SF_MODEL=Qwen/Qwen3-32B     # 必填；端口非 8000 时用 SF_API_BASE 覆盖
```

本地服务无需真实 key（预设自动填占位符 `ollama` / `EMPTY`）。

## 五档 profile 与角色映射

预设为每个厂商生成五个 profile，绑定关系（对齐内部质量分配：判分与导表精度敏感走主力，高频抽取与合成走轻量档降本）：

| profile | 角色 | 模型档 | 温度 | 输出上限 |
|---|---|---|---|---|
| `main` | orchestrator / sub_agent / skill_evolver / post_mortem / skill_router | 主力 | 0.7 | 16384 |
| `judge` | judge | 主力 | 0.0 | 16384 |
| `fast` | extraction / alias_resolver / skill_runtime | 轻量 | 0.0 | 32768 |
| `synthesis` | synthesis | 轻量 | 0.3 | 32768 |
| `reformat` | reformat（评测导表，需最大窗口） | 主力 | 0.0 | 65536 |

主力模型用 `SF_MODEL` 覆盖，轻量档用 `SF_FAST_MODEL` 覆盖（预设未配轻量档时回落主力）。输出上限会被厂商能力钳制（如 DeepSeek 8192、Kimi 订阅 32768）。

各预设的轻量档默认值（2026-07 核实；抽取输入较长，8K 上下文的小杯模型不可用）：

| 厂商 | 轻量档默认 | 备注 |
|---|---|---|
| 智谱 / Z.ai 按量 | `glm-4.7-flash` | 免费、30B、支持 FC+JSON |
| 阿里百炼 | `qwen3.5-flash` | ¥0.2/¥2、1M 上下文（`qwen-turbo` 已于 2026-07-13 下线） |
| 硅基流动 | `Qwen/Qwen3-30B-A3B-Instruct-2507` | 与内部抽取档同级；旧 id `Qwen/Qwen3-30B-A3B` 已下架 |
| MiniMax | `MiniMax-M2.7` | 无真正轻量档，M2.7 为在售最便宜档 |
| OpenAI | `gpt-5.4-mini` | 5.5 世代无 mini/nano，轻量档在 5.4 世代 |
| Gemini | `gemini-3.1-flash-lite` | `gemini-3.5-flash-lite` 不存在 |
| OpenRouter | `google/gemini-3.5-flash` | |
| Moonshot / DeepSeek / xAI / 火山 / coding plan 系 | 回落主力 | Moonshot turbo 已下线、火山 lite/mini id 需在控制台确认后用 `SF_FAST_MODEL` 指定；DeepSeek v4-flash 本身即便宜档 |

## 精细覆写

所有覆写与预设**深合并**——只改你写的字段，其余保持预设值：

```bash
# 单角色换绑（比如抽取角色换更便宜的模型档）
SF_ROLES__EXTRACTION=main

# 单 profile 字段覆写（profile 名里的 - 在环境变量里写成 _）
SF_PROFILES__MAIN__TEMPERATURE=0.3
SF_PROFILES__MAIN__ENABLE_THINKING=true
SF_PROFILES__FAST__MAX_TOKENS=16384

# 完全自定义一个 profile 并绑给某角色
SF_PROFILES__MYPROF__MODEL=glm-5-turbo
SF_PROFILES__MYPROF__API_BASE=https://open.bigmodel.cn/api/paas/v4
SF_PROFILES__MYPROF__API_KEY_ENV=ZHIPU_API_KEY
SF_ROLES__SKILL_ROUTER=myprof
```

`ModelProfile` 的完整字段（provider、thinking_style、rpm/tpm 限速、extra 透传等）见 `searchos/config/settings.py`。

## 厂商怪癖速查

| 怪癖 | 处理方式 |
|---|---|
| OpenAI / Gemini / OpenRouter 拒收未知 body 参数 | 预设 `thinking_style=none`，不注入任何 thinking 开关 |
| DashScope 用顶层 `enable_thinking` | 预设 `thinking_style=enable_thinking` |
| vLLM / 硅基流动用 `chat_template_kwargs.enable_thinking` | 预设 `thinking_style=chat_template_kwargs` |
| Claude Opus 4.7+ / GPT-5 系拒收 `temperature` | 预设 `temperature_ok=False`，全档省略 |
| Ollama / vLLM 要求非空 key | 预设 `api_key_fallback` 占位 |
| DeepSeek Anthropic 端点忽略 `top_k`、`cache_control` 等 | 无需处理，静默忽略 |

## 搜索后端

模型之外还需要一个 Web 搜索 API（配置向导会一并引导）：

| `SF_SEARCH_PROVIDER` | 服务 | Key 环境变量 | 说明 |
|---|---|---|---|
| `serper` | Serper.dev | `SERPER_API_KEY` | Google 结果，推荐；serper.dev 注册 |
| `tavily` | Tavily | `TAVILY_API_KEY` | 需 `pip install 'searchos[tavily]'` |
| `ragflow` | RagFlow | — | 蚂蚁内网接口，外部不可用 |

不设 `SF_SEARCH_PROVIDER` 时按已有 key 自动推断（serper → tavily），都没有则回落 ragflow（向后兼容内部用法）。页面抓取后端另由 `SF_BROWSER_BACKEND` 控制（默认 `jina`，建议配 `SF_JINA_API_KEY`）。

各端点与模型 id 核实于 2026-07 各厂商官方文档（`searchos/config/providers.py` 每个预设附 `doc_url`）。厂商迭代快，如遇 404/模型下线，用 `SF_API_BASE` / `SF_MODEL` 覆盖并提 issue。
