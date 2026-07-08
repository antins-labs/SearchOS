"""Provider presets — one-knob open-source model configuration.

Set ``SF_PROVIDER`` (plus the provider's API key) and every one of the 12
model roles gets a working profile binding, no settings surgery required::

    SF_PROVIDER=zhipu-coding          # GLM Coding Plan（Anthropic 协议）
    ZHIPU_API_KEY=xxx

    SF_PROVIDER=deepseek              # DeepSeek 按量 API（OpenAI 协议）
    DEEPSEEK_API_KEY=xxx

Optional knobs (all read from the environment, so they compose with .env):

    SF_MODEL        override the preset's main model id
    SF_FAST_MODEL   override the light-tier model (extraction/synthesis)
    SF_API_BASE     override the endpoint (e.g. 国际站 domains)
    SF_API_KEY_ENV  read the key from a different env var name

Presets only generate *defaults* for ``settings.profiles`` / ``settings.roles``;
explicit ``SF_PROFILES__*`` / ``SF_ROLES__*`` overrides still win (they are
deep-merged on top by ``Settings``).

Each preset expands into five tier profiles::

    main       orchestrator / sub_agent / skill_evolver / post_mortem / skill_router
    judge      judge                              (temperature 0)
    fast       extraction / alias_resolver / skill_runtime (temperature 0)
    synthesis  synthesis                          (temperature 0.3)
    reformat   reformat                           (temperature 0, large output)

Coding-plan presets speak the Anthropic protocol (the same endpoints the
vendors publish for Claude Code); pay-as-you-go presets speak OpenAI
chat/completions. NOTE: Claude Pro/Max 订阅的 OAuth token 不能在第三方框架中
使用（Anthropic ToS 限制）——``anthropic`` 预设只支持 Console API key。
部分厂商的 coding plan 条款仅授权交互式编程工具使用，接入前请自行确认。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderPreset:
    label: str
    provider: str  # "openai_compatible" | "openai" | "anthropic"
    api_base: str
    api_key_env: str
    main_model: str = ""      # empty → SF_MODEL is mandatory (local deployments)
    fast_model: str = ""      # empty → same as main
    api_key_fallback: str = ""  # local servers need a placeholder key
    temperature_ok: bool = True  # False → omit temperature entirely (gateway 400s)
    thinking_style: str = "none"  # see ModelProfile.thinking_style
    max_output: int = 65536   # provider output-token ceiling; tiers are clamped
    doc_url: str = ""
    notes: str = ""
    extra: dict = field(default_factory=dict)  # forwarded into every tier profile


# ---------------------------------------------------------------------------
# Registry — base_url / model id 均来自各厂商官方文档（2026-07 核实）。
# ---------------------------------------------------------------------------

PRESETS: dict[str, ProviderPreset] = {
    # --- Coding plan / Anthropic 协议 ---
    "anthropic": ProviderPreset(
        label="Anthropic 官方 API",
        provider="anthropic", api_base="",  # SDK default api.anthropic.com
        api_key_env="ANTHROPIC_API_KEY",
        main_model="claude-sonnet-5", fast_model="claude-haiku-4-5",
        # Opus 4.7+/Sonnet 5/Fable 5 reject temperature/top_p/top_k outright.
        temperature_ok=False,
        doc_url="https://platform.claude.com/docs/en/about-claude/models/overview",
        notes="仅支持 Console API key；Claude Pro/Max 订阅 OAuth token 禁止用于第三方框架（ToS）。",
    ),
    "zhipu-coding": ProviderPreset(
        label="智谱 GLM Coding Plan（中国站）",
        provider="anthropic", api_base="https://open.bigmodel.cn/api/anthropic",
        api_key_env="ZHIPU_API_KEY",
        main_model="glm-5.2", fast_model="glm-4.7",
        doc_url="https://docs.bigmodel.cn/cn/coding-plan/quick-start",
    ),
    "zai-coding": ProviderPreset(
        label="Z.ai GLM Coding Plan（国际站）",
        provider="anthropic", api_base="https://api.z.ai/api/anthropic",
        api_key_env="ZAI_API_KEY",
        main_model="glm-5.2", fast_model="glm-4.7",
        doc_url="https://docs.z.ai/devpack/tool/claude",
    ),
    "kimi-coding": ProviderPreset(
        label="Kimi For Coding 订阅（kimi.com）",
        provider="anthropic", api_base="https://api.kimi.com/coding",
        api_key_env="KIMI_API_KEY",
        main_model="kimi-for-coding",
        max_output=32768,
        doc_url="https://www.kimi.com/code/docs/en/third-party-tools/other-coding-agents.html",
        notes="Key 在 kimi.com/code/console 创建，订阅专属，与开放平台 Key 不通用。",
    ),
    "moonshot-anthropic": ProviderPreset(
        label="Moonshot 开放平台（Anthropic 协议，按量）",
        provider="anthropic", api_base="https://api.moonshot.cn/anthropic",
        api_key_env="MOONSHOT_API_KEY",
        main_model="kimi-k2.5",
        doc_url="https://platform.kimi.com/docs/guide/agent-support",
    ),
    "minimax-coding": ProviderPreset(
        label="MiniMax Coding Plan（中国站）",
        provider="anthropic", api_base="https://api.minimaxi.com/anthropic",
        api_key_env="MINIMAX_API_KEY",
        # MiniMax 无轻量档；M2.7 是在售最便宜档，作为高频小任务档。
        main_model="MiniMax-M3", fast_model="MiniMax-M2.7",
        doc_url="https://platform.minimax.io/docs/token-plan/claude-code",
        notes="国际站用 SF_API_BASE=https://api.minimax.io/anthropic。",
    ),
    "qwen-coding": ProviderPreset(
        label="阿里百炼 Qwen 编程套餐（中国站）",
        provider="anthropic",
        api_base="https://coding.dashscope.aliyuncs.com/apps/anthropic",
        api_key_env="DASHSCOPE_API_KEY",
        main_model="qwen3.7-plus",
        doc_url="https://help.aliyun.com/zh/model-studio/claude-code",
        notes="套餐 Key 为 sk-sp- 前缀专属 Key；条款仅授权编程工具交互式使用，接入前请自行确认。"
              "按量端点：https://dashscope.aliyuncs.com/apps/anthropic（普通百炼 Key）。",
    ),
    "volcengine-coding": ProviderPreset(
        label="火山方舟 Coding Plan",
        provider="anthropic", api_base="https://ark.cn-beijing.volces.com/api/coding",
        api_key_env="ARK_API_KEY",
        main_model="doubao-seed-code-preview-latest",
        doc_url="https://www.volcengine.com/docs/82379/1928262",
    ),
    "deepseek-anthropic": ProviderPreset(
        label="DeepSeek（Anthropic 协议，按量）",
        provider="anthropic", api_base="https://api.deepseek.com/anthropic",
        api_key_env="DEEPSEEK_API_KEY",
        main_model="deepseek-v4-flash",
        doc_url="https://api-docs.deepseek.com/guides/anthropic_api",
    ),

    # --- OpenAI 协议（官方 / 按量 / 聚合 / 本地）---
    "openai": ProviderPreset(
        label="OpenAI 官方 API",
        provider="openai", api_base="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        # gpt-5.5 世代无 mini/nano，轻量档停留在 5.4 世代（2026-07 核实）。
        main_model="gpt-5.5", fast_model="gpt-5.4-mini",
        temperature_ok=False,  # GPT-5 系推理模型固定 temperature
        doc_url="https://developers.openai.com/api/docs/models",
    ),
    "zhipu": ProviderPreset(
        label="智谱 GLM 按量 API（中国站）",
        provider="openai_compatible", api_base="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPU_API_KEY",
        # glm-4.7-flash：免费、30B、支持 FC+JSON —— 抽取/判分档首选。
        main_model="glm-5.2", fast_model="glm-4.7-flash",
        doc_url="https://docs.bigmodel.cn",
    ),
    "zai": ProviderPreset(
        label="Z.ai GLM 按量 API（国际站）",
        provider="openai_compatible", api_base="https://api.z.ai/api/paas/v4",
        api_key_env="ZAI_API_KEY",
        main_model="glm-5.2", fast_model="glm-4.7-flash",
        doc_url="https://docs.z.ai",
    ),
    "moonshot": ProviderPreset(
        label="Moonshot/Kimi 开放平台（按量）",
        provider="openai_compatible", api_base="https://api.moonshot.cn/v1",
        api_key_env="MOONSHOT_API_KEY",
        # kimi-k2-turbo-preview 已下线；moonshot-v1-8k 上下文太小（抽取输入常
        # 超 8K tokens），故轻量档回落主模型，可用 SF_FAST_MODEL 自行指定。
        main_model="kimi-k2.5",
        doc_url="https://platform.kimi.com/docs",
        notes="国际站用 SF_API_BASE=https://api.moonshot.ai/v1。",
    ),
    "deepseek": ProviderPreset(
        label="DeepSeek 按量 API",
        provider="openai_compatible", api_base="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
        main_model="deepseek-v4-flash",
        max_output=8192,
        doc_url="https://api-docs.deepseek.com",
        notes="旧模型名 deepseek-chat/deepseek-reasoner 已映射到 v4-flash；思考档用 deepseek-v4-pro。",
    ),
    "minimax": ProviderPreset(
        label="MiniMax 按量 API（中国站）",
        provider="openai_compatible", api_base="https://api.minimaxi.com/v1",
        api_key_env="MINIMAX_API_KEY",
        main_model="MiniMax-M3", fast_model="MiniMax-M2.7",
        doc_url="https://platform.minimax.io/docs/api-reference/text-openai-api",
        notes="国际站用 SF_API_BASE=https://api.minimax.io/v1。",
    ),
    "dashscope": ProviderPreset(
        label="阿里百炼 DashScope（按量）",
        provider="openai_compatible",
        api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
        # qwen3.5-flash：¥0.2/¥2、1M 上下文、FC+结构化输出（qwen-turbo 已于
        # 2026-07-13 下线，勿用）。
        main_model="qwen3.7-plus", fast_model="qwen3.5-flash",
        thinking_style="enable_thinking",
        doc_url="https://help.aliyun.com/zh/model-studio/",
        notes="国际站用 SF_API_BASE=https://dashscope-intl.aliyuncs.com/compatible-mode/v1。",
    ),
    "volcengine": ProviderPreset(
        label="火山方舟（按量）",
        provider="openai_compatible", api_base="https://ark.cn-beijing.volces.com/api/v3",
        api_key_env="ARK_API_KEY",
        main_model="doubao-seed-2.0-pro",
        doc_url="https://www.volcengine.com/docs/82379",
        notes="模型 id/接入点以方舟控制台为准，必要时用 SF_MODEL 覆盖；轻量档"
              "（doubao-seed-2-0-lite/mini，id 后缀以控制台为准）用 SF_FAST_MODEL 指定。",
    ),
    "openrouter": ProviderPreset(
        label="OpenRouter 聚合",
        provider="openai_compatible", api_base="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        main_model="anthropic/claude-sonnet-4.5", fast_model="google/gemini-3.5-flash",
        doc_url="https://openrouter.ai/docs",
        notes="模型 id 为 vendor/model 格式；免费档带 :free 后缀。",
    ),
    "siliconflow": ProviderPreset(
        label="硅基流动 SiliconFlow（中国站）",
        provider="openai_compatible", api_base="https://api.siliconflow.cn/v1",
        api_key_env="SILICONFLOW_API_KEY",
        # 30B-A3B 非思考直出、262K 上下文 —— 与内部抽取档（Qwen3.5-35B-A3B）同级。
        # 旧 id Qwen/Qwen3-30B-A3B 已下架，勿回退。
        main_model="deepseek-ai/DeepSeek-V3.2",
        fast_model="Qwen/Qwen3-30B-A3B-Instruct-2507",
        thinking_style="chat_template_kwargs",
        doc_url="https://docs.siliconflow.cn",
        notes="模型 id 带组织前缀且大小写敏感；国际站 SF_API_BASE=https://api.siliconflow.com/v1（账号不互通）。",
    ),
    "gemini": ProviderPreset(
        label="Google Gemini（OpenAI 兼容层）",
        provider="openai_compatible",
        api_base="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key_env="GEMINI_API_KEY",
        # 轻量档确切 id 是 3.1 flash-lite（gemini-3.5-flash-lite 不存在）。
        main_model="gemini-3.5-flash", fast_model="gemini-3.1-flash-lite",
        doc_url="https://ai.google.dev/gemini-api/docs/openai",
    ),
    "xai": ProviderPreset(
        label="xAI Grok",
        provider="openai_compatible", api_base="https://api.x.ai/v1",
        api_key_env="XAI_API_KEY",
        main_model="grok-4.3",
        doc_url="https://docs.x.ai/developers/quickstart",
    ),
    "ollama": ProviderPreset(
        label="Ollama 本地部署",
        provider="openai_compatible", api_base="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY", api_key_fallback="ollama",
        main_model="",  # SF_MODEL 必填
        doc_url="https://docs.ollama.com/api/openai-compatibility",
    ),
    "vllm": ProviderPreset(
        label="vLLM 本地部署",
        provider="openai_compatible", api_base="http://localhost:8000/v1",
        api_key_env="VLLM_API_KEY", api_key_fallback="EMPTY",
        main_model="",  # SF_MODEL 必填
        thinking_style="chat_template_kwargs",
        doc_url="https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
    ),
}

# 展示分组（TUI 向导表格与 web 预设列表共用）。必须覆盖全部 PRESETS —— 有
# 覆盖性测试保证；新增预设时记得同步归组。
PRESET_GROUPS: list[tuple[str, list[str]]] = [
    ("coding_plan", [
        "zhipu-coding", "zai-coding", "kimi-coding", "minimax-coding",
        "qwen-coding", "volcengine-coding",
    ]),
    ("pay_as_you_go", [
        "deepseek", "zhipu", "zai", "moonshot", "minimax", "dashscope",
        "volcengine", "moonshot-anthropic", "deepseek-anthropic",
        "openai", "anthropic", "openrouter", "siliconflow", "gemini", "xai",
    ]),
    ("local", ["ollama", "vllm"]),
]


def preset_info(name: str, preset: ProviderPreset | None = None) -> dict:
    """预设的展示视图（web 预设列表的一项）——绝不含任何密钥值。"""
    preset = preset or PRESETS[name]
    group = next((g for g, names in PRESET_GROUPS if name in names), "")
    return {
        "name": name,
        "label": preset.label,
        "group": group,
        "api_key_env": preset.api_key_env,
        "requires_key": not preset.api_key_fallback,
        "requires_model": not preset.main_model,
        "main_model": preset.main_model,
        "fast_model": preset.fast_model,
        "api_base": preset.api_base,
        "doc_url": preset.doc_url,
        "notes": preset.notes,
    }


ALIASES: dict[str, str] = {
    "glm": "zhipu",
    "bigmodel": "zhipu",
    "glm-coding": "zhipu-coding",
    "kimi": "moonshot",
    "qwen": "dashscope",
    "doubao": "volcengine",
    "ark": "volcengine",
    "ark-coding": "volcengine-coding",
    "doubao-coding": "volcengine-coding",
    "dashscope-coding": "qwen-coding",
    "claude": "anthropic",
}

# tier → (temperature, output-token ceiling)
_TIERS: dict[str, tuple[float, int]] = {
    "main":      (0.7, 16384),
    "judge":     (0.0, 16384),
    "fast":      (0.0, 32768),
    "synthesis": (0.3, 32768),
    # reformat emits full answer tables verbatim — needs the largest window.
    "reformat":  (0.0, 65536),
}

_ROLE_TIERS: dict[str, str] = {
    "orchestrator":     "main",
    "sub_agent":        "main",
    "skill_evolver":    "main",
    "post_mortem":      "main",
    "skill_router":     "main",
    "judge":            "judge",
    "extraction":       "fast",
    "alias_resolver":   "fast",
    "skill_runtime":    "fast",
    "synthesis":        "synthesis",
    "reformat":         "reformat",
}


def resolve_preset(name: str) -> ProviderPreset:
    key = name.strip().lower()
    key = ALIASES.get(key, key)
    preset = PRESETS.get(key)
    if preset is None:
        known = ", ".join(sorted(PRESETS))
        raise ValueError(
            f"Unknown SF_PROVIDER={name!r}. Available presets: {known} "
            f"(aliases: {', '.join(sorted(ALIASES))})"
        )
    return preset


def active_provider() -> str:
    """The SF_PROVIDER env value ('' when unset → built-in defaults apply)."""
    return os.environ.get("SF_PROVIDER", "").strip()


def provider_default_profiles() -> dict[str, dict] | None:
    """Preset-generated ``settings.profiles`` defaults, or None when SF_PROVIDER unset."""
    name = active_provider()
    if not name:
        return None
    preset = resolve_preset(name)

    main = os.environ.get("SF_MODEL", "").strip() or preset.main_model
    if not main:
        raise ValueError(
            f"Provider preset {name!r} has no default model — set SF_MODEL "
            f"(e.g. the model you serve locally). Docs: {preset.doc_url}"
        )
    fast = (
        os.environ.get("SF_FAST_MODEL", "").strip()
        or preset.fast_model
        or main
    )
    api_base = os.environ.get("SF_API_BASE", "").strip() or preset.api_base
    api_key_env = os.environ.get("SF_API_KEY_ENV", "").strip() or preset.api_key_env

    profiles: dict[str, dict] = {}
    for tier, (temp, out_tokens) in _TIERS.items():
        # 对齐内部质量分配：judge/reformat 走主力模型（判分与导表精度敏感），
        # 只有高频抽取（fast）与合成（synthesis）走轻量档。
        profiles[tier] = {
            "model": fast if tier in ("fast", "synthesis") else main,
            "provider": preset.provider,
            "api_base": api_base,
            "api_key_env": api_key_env,
            "api_key_fallback": preset.api_key_fallback,
            "temperature": temp if preset.temperature_ok else None,
            "max_tokens": min(out_tokens, preset.max_output),
            "thinking_style": preset.thinking_style,
            **({"extra": dict(preset.extra)} if preset.extra else {}),
        }
    return profiles


def provider_default_roles() -> dict[str, str] | None:
    """Preset-generated ``settings.roles`` defaults, or None when SF_PROVIDER unset."""
    if not active_provider():
        return None
    return dict(_ROLE_TIERS)


__all__ = [
    "PRESETS",
    "PRESET_GROUPS",
    "ALIASES",
    "ProviderPreset",
    "preset_info",
    "resolve_preset",
    "active_provider",
    "provider_default_profiles",
    "provider_default_roles",
]
