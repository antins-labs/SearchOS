# Model Provider Configuration

**English** | [简体中文](zh/providers.md)

SearchOS constructs its 11 model roles—such as `orchestrator`, `extraction`,
and `judge`—through `searchos/config/models.py:get_model_for(role)`, backed by
LangChain's `ChatOpenAI` and `ChatAnthropic` clients.

**The fastest setup path is the interactive wizard.** The first
`python -m searchos` run opens it automatically, or you can rerun it at any time
with `python -m searchos --setup`. For a manual setup, two environment variables
are enough:

```bash
# .env (see .env.example in the repository root)
SF_PROVIDER=zhipu-coding
ZHIPU_API_KEY=xxx
```

`SF_PROVIDER` generates default bindings for every role across five profiles:
`main`, `judge`, `fast`, `synthesis`, and `reformat`. Advanced users can
override individual values with `SF_PROFILES__*` and `SF_ROLES__*`; these values
are recursively merged without discarding other preset fields.

## Preset overview

### Coding plans using the Anthropic protocol

These vendor plans expose Anthropic-compatible endpoints originally intended
for coding clients. SearchOS connects through `ChatAnthropic` with a custom
`base_url`.

| `SF_PROVIDER` | Vendor | Endpoint | Key environment variable | Default models |
|---|---|---|---|---|
| `zhipu-coding` | Zhipu GLM Coding Plan (China) | `open.bigmodel.cn/api/anthropic` | `ZHIPU_API_KEY` | glm-5.2 / glm-4.7 |
| `zai-coding` | Z.ai GLM Coding Plan (international) | `api.z.ai/api/anthropic` | `ZAI_API_KEY` | glm-5.2 / glm-4.7 |
| `kimi-coding` | Kimi For Coding | `api.kimi.com/coding` | `KIMI_API_KEY` | kimi-for-coding |
| `moonshot-anthropic` | Moonshot pay-as-you-go | `api.moonshot.cn/anthropic` | `MOONSHOT_API_KEY` | kimi-k2.5 |
| `minimax-coding` | MiniMax Coding Plan | `api.minimaxi.com/anthropic` | `MINIMAX_API_KEY` | MiniMax-M3 |
| `qwen-coding` | Alibaba Cloud Model Studio Coding Plan | `coding.dashscope.aliyuncs.com/apps/anthropic` | `DASHSCOPE_API_KEY` | qwen3.7-plus |
| `volcengine-coding` | Volcengine Ark Coding Plan | `ark.cn-beijing.volces.com/api/coding` | `ARK_API_KEY` | doubao-seed-code-preview-latest |
| `deepseek-anthropic` | DeepSeek pay-as-you-go | `api.deepseek.com/anthropic` | `DEEPSEEK_API_KEY` | deepseek-v4-flash |
| `anthropic` | Anthropic API | `api.anthropic.com` | `ANTHROPIC_API_KEY` | claude-sonnet-5 / claude-haiku-4-5 |

Important notes:

- **Keys are product-specific.** Kimi coding-plan keys come from
  `kimi.com/code/console` and are separate from Moonshot platform keys.
  Alibaba coding-plan keys use the `sk-sp-` prefix. Zhipu team coding keys and
  MiniMax subscription keys are also separate from their pay-as-you-go keys.
- **Check usage terms.** Some coding plans authorize only interactive use in
  supported coding tools. Confirm the vendor's current terms before using a
  subscription key in an agent framework. Pay-as-you-go API keys are not
  subject to coding-plan restrictions.
- **Claude subscription tokens are unsupported.** OAuth tokens produced by
  `claude setup-token` are restricted to Claude Code and claude.ai under
  Anthropic's terms. The `anthropic` preset accepts Console API keys only.
- Newer Anthropic models such as Opus 4.7+ and Sonnet 5 reject `temperature`;
  the relevant presets omit it automatically. Other Anthropic-compatible
  vendor endpoints are unaffected.

### Pay-as-you-go APIs using the OpenAI protocol

| `SF_PROVIDER` | Vendor | Endpoint | Key environment variable | Default models |
|---|---|---|---|---|
| `deepseek` | DeepSeek | `api.deepseek.com` | `DEEPSEEK_API_KEY` | deepseek-v4-flash |
| `zhipu` | Zhipu (China) | `open.bigmodel.cn/api/paas/v4` | `ZHIPU_API_KEY` | glm-5.2 / glm-4.7-flash |
| `zai` | Z.ai (international) | `api.z.ai/api/paas/v4` | `ZAI_API_KEY` | glm-5.2 / glm-4.7-flash |
| `moonshot` (alias `kimi`) | Moonshot | `api.moonshot.cn/v1` | `MOONSHOT_API_KEY` | kimi-k2.5 |
| `minimax` | MiniMax | `api.minimaxi.com/v1` | `MINIMAX_API_KEY` | MiniMax-M3 |
| `dashscope` (alias `qwen`) | Alibaba Cloud Model Studio | `dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` | qwen3.7-plus |
| `volcengine` (aliases `doubao`, `ark`) | Volcengine Ark | `ark.cn-beijing.volces.com/api/v3` | `ARK_API_KEY` | doubao-seed-2.0-pro |
| `openai` | OpenAI API | `api.openai.com/v1` | `OPENAI_API_KEY` | gpt-5.5 |
| `openrouter` | OpenRouter | `openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | anthropic/claude-sonnet-4.5 |
| `siliconflow` | SiliconFlow (China) | `api.siliconflow.cn/v1` | `SILICONFLOW_API_KEY` | deepseek-ai/DeepSeek-V3.2 |
| `gemini` | Google Gemini OpenAI compatibility layer | `generativelanguage.googleapis.com/v1beta/openai/` | `GEMINI_API_KEY` | gemini-3.5-flash |
| `xai` | xAI | `api.x.ai/v1` | `XAI_API_KEY` | grok-4.3 |

Important notes:

- DeepSeek limits output to 8,192 tokens, so SearchOS clamps the `reformat`
  profile automatically. For very large table exports, use a provider with a
  larger output window. Legacy `deepseek-chat` and `deepseek-reasoner` names are
  mapped to v4-flash.
- OpenAI GPT-5 reasoning models reject `temperature`; their presets omit it.
- Override `SF_API_BASE` to select international MiniMax, Moonshot, Alibaba, or
  SiliconFlow endpoints. China and international SiliconFlow accounts are not
  interchangeable.
- Volcengine model IDs may depend on your console configuration. Override
  `SF_MODEL` when necessary.

### Local deployments

```bash
SF_PROVIDER=ollama
SF_MODEL=qwen3:32b          # Required

SF_PROVIDER=vllm
SF_MODEL=Qwen/Qwen3-32B     # Required; override SF_API_BASE if the port is not 8000
```

Local services do not require a real key. The presets provide the non-empty
placeholders `ollama` and `EMPTY` where the client requires one.

## Five profiles and their role bindings

Each preset creates five profiles. Quality-sensitive judging and export roles
use the primary model, while high-volume extraction and synthesis roles use the
lighter model to control cost.

| Profile | Roles | Model tier | Temperature | Output limit |
|---|---|---|---|---|
| `main` | orchestrator / sub_agent / skill_evolver / post_mortem / skill_router | Primary | 0.7 | 16384 |
| `judge` | judge | Primary | 0.0 | 16384 |
| `fast` | extraction / alias_resolver / skill_runtime | Light | 0.0 | 32768 |
| `synthesis` | synthesis | Light | 0.3 | 32768 |
| `reformat` | reformat (evaluation table export) | Primary | 0.0 | 65536 |

Use `SF_MODEL` to override the primary model and `SF_FAST_MODEL` to override the
light model. Presets without a separate light model fall back to the primary
one. Provider capabilities may clamp output limits, such as 8,192 for DeepSeek
or 32,768 for the Kimi coding plan.

Light-profile defaults were checked against vendor documentation in July 2026.
Extraction inputs are often long, so models limited to an 8K context window are
not suitable.

| Vendor | Light-profile default | Notes |
|---|---|---|
| Zhipu / Z.ai pay-as-you-go | `glm-4.7-flash` | Free tier, 30B, function calling and JSON support |
| Alibaba Cloud Model Studio | `qwen3.5-flash` | 1M context; `qwen-turbo` retires on July 13, 2026 |
| SiliconFlow | `Qwen/Qwen3-30B-A3B-Instruct-2507` | The older `Qwen/Qwen3-30B-A3B` ID is unavailable |
| MiniMax | `MiniMax-M2.7` | The least expensive currently listed tier rather than a dedicated light model |
| OpenAI | `gpt-5.4-mini` | The 5.5 generation has no mini/nano model |
| Gemini | `gemini-3.1-flash-lite` | `gemini-3.5-flash-lite` does not exist |
| OpenRouter | `google/gemini-3.5-flash` | — |
| Moonshot, DeepSeek, xAI, Volcengine, and coding-plan presets | Primary-model fallback | Override `SF_FAST_MODEL` when your account exposes a suitable light model |

## Fine-grained overrides

Overrides are recursively merged with the selected preset, so changing one
field does not discard the others:

```bash
# Bind one role to a different profile
SF_ROLES__EXTRACTION=main

# Override fields on an existing profile (replace - with _ in environment paths)
SF_PROFILES__MAIN__TEMPERATURE=0.3
SF_PROFILES__MAIN__ENABLE_THINKING=true
SF_PROFILES__FAST__MAX_TOKENS=16384

# Define a custom profile and bind it to a role
SF_PROFILES__MYPROF__MODEL=glm-5-turbo
SF_PROFILES__MYPROF__API_BASE=https://open.bigmodel.cn/api/paas/v4
SF_PROFILES__MYPROF__API_KEY_ENV=ZHIPU_API_KEY
SF_ROLES__SKILL_ROUTER=myprof
```

See `searchos/config/settings.py` for all `ModelProfile` fields, including
provider, thinking style, RPM/TPM limits, and extra request parameters.

## Provider compatibility notes

| Behavior | SearchOS handling |
|---|---|
| OpenAI, Gemini, and OpenRouter reject unknown request fields | `thinking_style=none`; no thinking switch is injected |
| DashScope expects top-level `enable_thinking` | `thinking_style=enable_thinking` |
| vLLM and SiliconFlow use `chat_template_kwargs.enable_thinking` | `thinking_style=chat_template_kwargs` |
| Claude Opus 4.7+ and GPT-5 models reject `temperature` | `temperature_ok=False`; all profiles omit it |
| Ollama and vLLM require a non-empty key | Presets provide `api_key_fallback` placeholders |
| DeepSeek's Anthropic endpoint ignores `top_k`, `cache_control`, and similar fields | No special handling is required |

## Search backends

SearchOS also needs a Web search API. The setup wizard configures it alongside
the model provider.

| `SF_SEARCH_PROVIDER` | Service | Key environment variable | Notes |
|---|---|---|---|
| `serper` | Serper.dev | `SERPER_API_KEY` | Recommended Google results backend |
| `tavily` | Tavily | `TAVILY_API_KEY` | Requires `pip install 'searchos[tavily]'` |
| `ragflow` | RagFlow | — | Ant Group internal backend; unavailable to external users |

Without `SF_SEARCH_PROVIDER`, SearchOS infers Serper and then Tavily from the
available keys. If neither key exists, it falls back to RagFlow for backward
compatibility. Page retrieval is configured separately through
`SF_BROWSER_BACKEND`; the default is `jina`, and `SF_JINA_API_KEY` is
recommended to avoid low unauthenticated rate limits.

Vendor endpoints and model IDs were checked against official documentation in
July 2026. Each preset in `searchos/config/providers.py` includes its source
`doc_url`. Providers change quickly; if an endpoint or model is retired,
override `SF_API_BASE` or `SF_MODEL` and open an issue with the updated details.
