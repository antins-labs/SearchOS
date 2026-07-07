"""Provider 预设层 + settings 部分覆写语义的回归测试。

不发任何真实请求 — 只验证配置解析和 LangChain 客户端构造出的 kwargs。
"""

from __future__ import annotations

import pytest

import searchos.config.models as models_mod
from searchos.config.providers import PRESETS, resolve_preset
from searchos.config.settings import ROLE_NAMES, Settings


def _fresh_settings(monkeypatch, **env: str) -> Settings:
    """Build Settings from a controlled env (provider knobs cleared first)."""
    for var in ("SF_PROVIDER", "SF_MODEL", "SF_FAST_MODEL", "SF_API_BASE",
                "SF_API_KEY_ENV", "SF_ROLES", "SF_PROFILES",
                "SF_BUILTIN_OPENAI_BASE", "SF_BUILTIN_ANTHROPIC_BASE"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings()


# ---------------------------------------------------------------------------
# 默认行为不变（向后兼容）
# ---------------------------------------------------------------------------

def test_builtin_defaults_without_provider(monkeypatch):
    # 内置回落 profiles 的网关端点不入库，从 SF_BUILTIN_*_BASE 环境变量读取
    s = _fresh_settings(monkeypatch, SF_BUILTIN_OPENAI_BASE="https://gw.example.com/v1")
    assert "glm5-strong" in s.profiles
    assert s.profiles["glm5-strong"].api_base == "https://gw.example.com/v1"
    assert set(s.roles) == set(ROLE_NAMES)
    # 旧 profile 保持 chat_template_kwargs 的 thinking 注入方式
    assert s.profiles["glm5-strong"].thinking_style == "chat_template_kwargs"


def test_builtin_defaults_empty_base_without_env(monkeypatch):
    s = _fresh_settings(monkeypatch)
    assert s.profiles["glm5-strong"].api_base == ""
    assert s.profiles["claude-opus-4-7"].api_base == ""


def test_partial_role_override_keeps_other_bindings(monkeypatch):
    s = _fresh_settings(monkeypatch, SF_ROLES__JUDGE="glm5-thinking")
    assert s.roles["judge"] == "glm5-thinking"
    assert len(s.roles) == len(ROLE_NAMES)  # 其余 11 个绑定未丢
    assert s.roles["orchestrator"] == "glm5-strong"


def test_partial_profile_override_merges_and_normalizes_key(monkeypatch):
    s = _fresh_settings(monkeypatch, SF_PROFILES__GLM5_STRONG__TEMPERATURE="0.1")
    p = s.profiles["glm5-strong"]
    assert p.temperature == 0.1
    assert p.model == "GLM-5"  # 未覆写字段保留默认


def test_brand_new_profile_via_env(monkeypatch):
    s = _fresh_settings(
        monkeypatch,
        SF_PROFILES__CUSTOM__MODEL="my-model",
        SF_PROFILES__CUSTOM__API_BASE="https://example.com/v1",
    )
    assert s.profiles["custom"].model == "my-model"
    assert "glm5-strong" in s.profiles


# ---------------------------------------------------------------------------
# SF_PROVIDER 预设
# ---------------------------------------------------------------------------

def test_all_presets_generate_complete_bindings(monkeypatch):
    for name in PRESETS:
        env = {"SF_PROVIDER": name}
        if not PRESETS[name].main_model:  # ollama / vllm
            env["SF_MODEL"] = "test-model"
        s = _fresh_settings(monkeypatch, **env)
        assert set(s.roles) == set(ROLE_NAMES), name
        for role, profile_name in s.roles.items():
            assert profile_name in s.profiles, (name, role)


def test_coding_plan_preset_speaks_anthropic(monkeypatch):
    s = _fresh_settings(monkeypatch, SF_PROVIDER="zhipu-coding")
    main = s.profiles[s.roles["orchestrator"]]
    assert main.provider == "anthropic"
    assert main.api_base == "https://open.bigmodel.cn/api/anthropic"
    assert main.model == "glm-5.2"
    assert main.api_key_env == "ZHIPU_API_KEY"
    fast = s.profiles[s.roles["extraction"]]
    assert fast.model == "glm-4.7"


def test_alias_and_model_override(monkeypatch):
    assert resolve_preset("kimi") is PRESETS["moonshot"]
    s = _fresh_settings(
        monkeypatch, SF_PROVIDER="kimi", SF_MODEL="kimi-k2.7-code",
        SF_API_BASE="https://api.moonshot.ai/v1",
    )
    main = s.profiles[s.roles["orchestrator"]]
    assert main.model == "kimi-k2.7-code"
    assert main.api_base == "https://api.moonshot.ai/v1"


def test_partial_override_composes_with_provider(monkeypatch):
    s = _fresh_settings(
        monkeypatch, SF_PROVIDER="deepseek",
        SF_PROFILES__MAIN__TEMPERATURE="0.2",
    )
    assert s.profiles["main"].temperature == 0.2
    assert s.profiles["main"].model == "deepseek-v4-flash"
    # DeepSeek 输出上限 8192 —— reformat 档被钳制
    assert s.profiles["reformat"].max_tokens == 8192


def test_light_tier_goes_to_fast_model_only(monkeypatch):
    """抽取/合成走轻量档；judge/reformat 精度敏感，跟主力模型走。"""
    s = _fresh_settings(monkeypatch, SF_PROVIDER="dashscope")
    assert s.profiles[s.roles["extraction"]].model == "qwen3.5-flash"
    assert s.profiles[s.roles["synthesis"]].model == "qwen3.5-flash"
    assert s.profiles[s.roles["judge"]].model == "qwen3.7-plus"
    assert s.profiles[s.roles["reformat"]].model == "qwen3.7-plus"
    assert s.profiles[s.roles["orchestrator"]].model == "qwen3.7-plus"


def test_fast_model_env_override(monkeypatch):
    s = _fresh_settings(
        monkeypatch, SF_PROVIDER="zhipu", SF_FAST_MODEL="glm-4.7-flashx",
    )
    assert s.profiles[s.roles["extraction"]].model == "glm-4.7-flashx"
    assert s.profiles[s.roles["orchestrator"]].model == "glm-5.2"


def test_local_preset_requires_model(monkeypatch):
    with pytest.raises((ValueError, Exception)) as ei:
        _fresh_settings(monkeypatch, SF_PROVIDER="ollama")
    assert "SF_MODEL" in str(ei.value)


def test_unknown_provider_lists_presets(monkeypatch):
    with pytest.raises(Exception) as ei:
        _fresh_settings(monkeypatch, SF_PROVIDER="nope")
    assert "zhipu-coding" in str(ei.value)


# ---------------------------------------------------------------------------
# get_model_for 端到端构造（不发请求）
# ---------------------------------------------------------------------------

def _bind(monkeypatch, s: Settings) -> None:
    monkeypatch.setattr(models_mod, "settings", s)


def test_openai_preset_sends_no_thinking_extra_body(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    s = _fresh_settings(monkeypatch, SF_PROVIDER="openai")
    _bind(monkeypatch, s)
    m = models_mod.get_model_for("orchestrator")
    # 官方 OpenAI 会 400 未知参数 —— extra_body 必须为空
    assert not getattr(m, "extra_body", None)
    assert m.temperature is None  # GPT-5 系不接受 temperature


def test_legacy_profile_still_sends_chat_template_kwargs(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    s = _fresh_settings(monkeypatch)
    _bind(monkeypatch, s)
    m = models_mod.get_model_for("orchestrator")
    assert m.extra_body == {"chat_template_kwargs": {"enable_thinking": False}}


def test_dashscope_thinking_style(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    s = _fresh_settings(monkeypatch, SF_PROVIDER="qwen")  # alias → dashscope
    _bind(monkeypatch, s)
    m = models_mod.get_model_for("orchestrator")
    assert m.extra_body == {"enable_thinking": False}


def test_ollama_placeholder_key(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    s = _fresh_settings(monkeypatch, SF_PROVIDER="ollama", SF_MODEL="qwen3:32b")
    _bind(monkeypatch, s)
    m = models_mod.get_model_for("extraction")
    assert m.openai_api_key.get_secret_value() == "ollama"


def test_anthropic_coding_plan_builds_chat_anthropic(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", "sk-test")
    s = _fresh_settings(monkeypatch, SF_PROVIDER="kimi-coding")
    _bind(monkeypatch, s)
    m = models_mod.get_model_for("orchestrator")
    from langchain_anthropic import ChatAnthropic

    assert isinstance(m, ChatAnthropic)
    assert m.model == "kimi-for-coding"
    assert "api.kimi.com/coding" in str(m.anthropic_api_url)
    assert m.max_tokens == 16384


def test_anthropic_official_omits_temperature(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    s = _fresh_settings(monkeypatch, SF_PROVIDER="anthropic")
    _bind(monkeypatch, s)
    m = models_mod.get_model_for("orchestrator")
    assert m.temperature is None
