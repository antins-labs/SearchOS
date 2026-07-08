"""models.json — 用户自建的两级模型配置（Provider 连接 + Model Card）。

这是模型配置的主来源：``models.json``（与 .env 同级，``SF_MODELS_FILE``
可覆盖路径）存 providers / models / roles 三张表，密钥仍只在 .env（由
``api_key_env`` 引用）。``settings.profiles`` / ``settings.roles`` 由本模块
编译生成（见 ``compile_to_profiles``），下游 ``get_model_for(role)`` 零改动。

优先级：models.json 存在 → 唯一来源（SF_PROVIDER / SF_PROFILES__* 等遗留
env 被忽略并 warn 一次）；不存在 → 旧链路兜底（SF_PROVIDER 预设 →
builtin）；全无 → ``default_models_config()`` 的 OpenRouter 模板作为
"虚拟配置" 呈现，首次编辑才落盘。

容错语义与 web_settings.json 刻意不同：models.json 是主配置，损坏/非法时
**strict fail loud**（``ModelsConfigError`` 带路径与修复指引），绝不静默
回落旧链路——否则"改了没生效"极难排查。

限速桶：ModelProfile 的限速器键是 (api_base, model, api_key_env)，provider
级 rpm/tpm 展平后同 provider 不同 model 的 card 各自成桶（比"真 provider
全局桶"宽松；改 limiter 键属 future work）。

只依赖 stdlib + pydantic + profiles.py —— CLI 配置向导在 settings 首次
import 之前就要用到本模块。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from searchos.config.env_file import find_env_path
from searchos.config.profiles import ROLE_NAMES, ModelProfile

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

Protocol = Literal["openai_compatible", "openai", "anthropic"]
ThinkingStyle = Literal["chat_template_kwargs", "enable_thinking", "none"]


class ModelsConfigError(ValueError):
    """models.json 缺失字段 / 引用悬空 / JSON 损坏 — message 含路径与修复指引。"""


class ProviderConn(BaseModel, extra="forbid"):
    """一个 API 端点连接：协议 + base URL + 密钥所在的环境变量名。"""

    protocol: Protocol = "openai_compatible"
    api_base: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    api_key_fallback: str = ""  # 本地部署（Ollama/vLLM）的占位 key
    thinking_style: ThinkingStyle = "none"
    rpm: int = 0  # provider 级配额默认值；0 = 不限
    tpm: int = 0
    label: str = ""    # 展示名（web 列表用，可选）
    doc_url: str = ""  # key 获取 / 文档链接（可选）


class ModelCard(BaseModel, extra="forbid"):
    """一张模型卡：引用某 provider + 模型 id + 生成参数。"""

    provider: str
    model: str
    max_tokens: int = 32768
    temperature: float | None = 0.7  # None = 不传该参数（推理模型会 400）
    enable_thinking: bool = False
    rpm: int | None = None  # None → 继承 provider.rpm
    tpm: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)  # 透传 SDK 的额外参数


class ModelsConfig(BaseModel, extra="forbid"):
    version: int = 1
    providers: dict[str, ProviderConn] = Field(default_factory=dict)
    models: dict[str, ModelCard] = Field(default_factory=dict)
    # 必含 "default"；其余 key ∈ ROLE_NAMES，value ∈ models
    roles: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_references(self) -> "ModelsConfig":
        for name in (*self.providers, *self.models):
            if not _NAME_RE.fullmatch(name):
                raise ValueError(
                    f"Invalid name {name!r} — use letters/digits with . _ - (max 64 chars)")
        for name, card in self.models.items():
            if not card.model.strip():
                raise ValueError(f"Model card {name!r} has an empty 'model' id")
            if card.provider not in self.providers:
                raise ValueError(
                    f"Model card {name!r} references unknown provider {card.provider!r}. "
                    f"Available: {sorted(self.providers) or '(none)'}")
        if "default" not in self.roles:
            raise ValueError(
                'roles must contain a "default" entry naming the model card most roles use')
        valid_keys = set(ROLE_NAMES) | {"default"}
        for role, card_name in self.roles.items():
            if role not in valid_keys:
                raise ValueError(
                    f"Unknown role {role!r} in roles. Valid: default, {', '.join(ROLE_NAMES)}")
            if card_name not in self.models:
                raise ValueError(
                    f"Role {role!r} is bound to unknown model card {card_name!r}. "
                    f"Available: {sorted(self.models) or '(none)'}")
        return self


# --- 路径与持久化 ---

def models_config_path(start: Path | None = None) -> Path:
    """SF_MODELS_FILE 优先；否则与 .env 同级的 models.json（同一套向上查找）。"""
    override = os.environ.get("SF_MODELS_FILE", "").strip()
    if override:
        return Path(override)
    return find_env_path(start).parent / "models.json"


def load_models_config(path: Path | None = None) -> ModelsConfig:
    """严格加载：JSON 损坏或校验失败 → ModelsConfigError（fail loud）。"""
    path = path or models_config_path()
    try:
        return ModelsConfig.model_validate_json(path.read_text())
    except FileNotFoundError:
        raise
    except Exception as e:
        raise ModelsConfigError(
            f"Invalid models config at {path}: {e}\n"
            f"Fix the file, or delete it and run `searchos --setup` "
            f"(or use the web Settings page) to regenerate."
        ) from e


def save_models_config(cfg: ModelsConfig, path: Path | None = None) -> None:
    """原子写（tmp + os.replace），对齐 .env / web_settings.json 的写盘方式。"""
    path = path or models_config_path()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(cfg.model_dump_json(indent=2) + "\n")
    os.replace(tmp, path)


# --- 编译到运行时事实源 ---

def compile_to_profiles(cfg: ModelsConfig) -> tuple[dict[str, ModelProfile], dict[str, str]]:
    """展平成 settings.profiles / settings.roles（card 名即 profile 名）。"""
    profiles: dict[str, ModelProfile] = {}
    for name, card in cfg.models.items():
        prov = cfg.providers[card.provider]
        profiles[name] = ModelProfile(
            model=card.model,
            provider=prov.protocol,
            api_base=prov.api_base,
            api_key_env=prov.api_key_env,
            api_key_fallback=prov.api_key_fallback,
            thinking_style=prov.thinking_style,
            temperature=card.temperature,
            max_tokens=card.max_tokens,
            enable_thinking=card.enable_thinking,
            rpm=card.rpm if card.rpm is not None else prov.rpm,
            tpm=card.tpm if card.tpm is not None else prov.tpm,
            extra=dict(card.extra),
        )
    default = cfg.roles["default"]
    roles = {role: cfg.roles.get(role, default) for role in ROLE_NAMES}
    return profiles, roles


def compiled_from_file(path: Path | None = None) -> tuple[dict[str, ModelProfile], dict[str, str]] | None:
    """models.json 不存在 → None（settings 走旧链路）；存在但非法 → raise。"""
    path = path or models_config_path()
    if not path.exists():
        return None
    return compile_to_profiles(load_models_config(path))


def check_runnable(cfg: ModelsConfig | None = None) -> list[str]:
    """发起搜索前的 preflight：返回缺失密钥的可操作描述清单（空 = 可跑）。

    只检查被 roles 引用（含 default 继承）的 card，未被使用的卡缺 key 不拦截。
    """
    if cfg is None:
        path = models_config_path()
        if not path.exists():
            return []  # 旧链路（预设/builtin）沿用原有懒失败语义
        cfg = load_models_config(path)
    used_cards = {cfg.roles.get(role, cfg.roles["default"]) for role in ROLE_NAMES}
    missing: list[str] = []
    seen_envs: set[str] = set()
    for card_name in sorted(used_cards):
        prov = cfg.providers[cfg.models[card_name].provider]
        if prov.api_key_fallback or os.environ.get(prov.api_key_env):
            continue
        if prov.api_key_env in seen_envs:
            continue
        seen_envs.add(prov.api_key_env)
        missing.append(
            f"Model '{card_name}' needs {prov.api_key_env} — "
            f"set it in Settings → Models or add it to .env")
    return missing


# --- 默认模板与遗留配置折叠 ---

def default_models_config() -> ModelsConfig:
    """开箱默认：OpenRouter 聚合网关 + 强/快两张卡（只差填 key）。"""
    return ModelsConfig(
        providers={
            "openrouter": ProviderConn(
                protocol="openai_compatible",
                api_base="https://openrouter.ai/api/v1",
                api_key_env="OPENROUTER_API_KEY",
                label="OpenRouter",
                doc_url="https://openrouter.ai/docs",
            ),
        },
        models={
            "strong": ModelCard(provider="openrouter", model="anthropic/claude-sonnet-4.5",
                                max_tokens=32768, temperature=0.7),
            "fast": ModelCard(provider="openrouter", model="google/gemini-3.5-flash",
                              max_tokens=32768, temperature=0.0),
        },
        roles={
            "default": "strong",
            "extraction": "fast", "alias_resolver": "fast",
            "skill_runtime": "fast", "synthesis": "fast",
        },
    )


def config_from_legacy(
    profiles: dict[str, Any],
    roles: dict[str, str],
    provider_name: str = "",
) -> ModelsConfig:
    """把旧的展平 profiles/roles 折叠成两级实体（迁移与虚拟配置共用）。

    按连接元组聚类成 provider；每个旧 profile 成为一张同名 card；roles 以
    orchestrator 的绑定为 default，其余删稀疏。
    """
    norm = {
        name: (p if isinstance(p, ModelProfile) else ModelProfile.model_validate(p))
        for name, p in profiles.items()
    }

    providers: dict[str, ProviderConn] = {}
    conn_names: dict[tuple, str] = {}
    for p in norm.values():
        conn = (p.provider, p.api_base, p.api_key_env, p.api_key_fallback, p.thinking_style)
        if conn in conn_names:
            continue
        base = provider_name if provider_name and not providers else (
            p.api_key_env.removesuffix("_API_KEY").lower() or "provider")
        if not _NAME_RE.fullmatch(base):
            base = "provider"
        name, i = base, 2
        while name in providers:
            name, i = f"{base}-{i}", i + 1
        conn_names[conn] = name
        providers[name] = ProviderConn(
            protocol=p.provider, api_base=p.api_base,
            api_key_env=p.api_key_env, api_key_fallback=p.api_key_fallback,
            thinking_style=p.thinking_style,
        )

    cards = {
        name: ModelCard(
            provider=conn_names[(p.provider, p.api_base, p.api_key_env,
                                 p.api_key_fallback, p.thinking_style)],
            model=p.model, max_tokens=p.max_tokens, temperature=p.temperature,
            enable_thinking=p.enable_thinking,
            rpm=p.rpm or None, tpm=p.tpm or None, extra=dict(p.extra),
        )
        for name, p in norm.items()
    }

    default = roles.get("orchestrator") or next(iter(cards))
    sparse: dict[str, str] = {"default": default}
    for role in ROLE_NAMES:
        bound = roles.get(role, default)
        if bound != default and bound in cards:
            sparse[role] = bound
    return ModelsConfig(providers=providers, models=cards, roles=sparse)


def virtual_models_config() -> ModelsConfig:
    """models.json 不存在时 UI 呈现的"当前生效配置"（编辑即物化的底稿）。"""
    from searchos.config.providers import (
        active_provider,
        provider_default_profiles,
        provider_default_roles,
    )
    from searchos.config.profiles import builtin_profiles, builtin_roles

    if active_provider():
        try:
            preset_profiles = provider_default_profiles()
            preset_roles = provider_default_roles()
            if preset_profiles is not None and preset_roles is not None:
                return config_from_legacy(preset_profiles, preset_roles, active_provider())
        except ValueError:
            pass  # 预设不完整（如 local 缺 SF_MODEL）→ 落到下面的分支
    if os.environ.get("OPENAI_API_KEY"):
        return config_from_legacy(builtin_profiles(), builtin_roles())
    return default_models_config()


__all__ = [
    "ModelCard",
    "ModelsConfig",
    "ModelsConfigError",
    "ProviderConn",
    "check_runnable",
    "compile_to_profiles",
    "compiled_from_file",
    "config_from_legacy",
    "default_models_config",
    "load_models_config",
    "models_config_path",
    "save_models_config",
    "virtual_models_config",
]
