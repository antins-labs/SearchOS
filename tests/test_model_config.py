"""models.json 两级模型配置 — schema 校验 / 编译 / 持久化 / 遗留折叠。"""

from __future__ import annotations

import pytest

from searchos.config.model_config import (
    ModelCard,
    ModelsConfig,
    ModelsConfigError,
    ProviderConn,
    check_runnable,
    compile_to_profiles,
    compiled_from_file,
    config_from_legacy,
    default_models_config,
    load_models_config,
    models_config_path,
    save_models_config,
    virtual_models_config,
)
from searchos.config.profiles import ROLE_NAMES, builtin_profiles, builtin_roles


def _cfg(**overrides) -> dict:
    base = {
        "providers": {"p1": {"api_base": "https://x/v1", "api_key_env": "X_KEY"}},
        "models": {"m1": {"provider": "p1", "model": "some-model"}},
        "roles": {"default": "m1"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# schema 校验
# ---------------------------------------------------------------------------

def test_dangling_provider_ref_rejected():
    with pytest.raises(ValueError, match="unknown provider"):
        ModelsConfig.model_validate(_cfg(models={"m1": {"provider": "nope", "model": "x"}}))


def test_roles_must_contain_default():
    with pytest.raises(ValueError, match="default"):
        ModelsConfig.model_validate(_cfg(roles={"judge": "m1"}))


def test_unknown_role_rejected():
    with pytest.raises(ValueError, match="Unknown role"):
        ModelsConfig.model_validate(_cfg(roles={"default": "m1", "jugde": "m1"}))  # typo


def test_role_bound_to_unknown_card_rejected():
    with pytest.raises(ValueError, match="unknown model card"):
        ModelsConfig.model_validate(_cfg(roles={"default": "m1", "judge": "nope"}))


def test_invalid_names_and_empty_model_rejected():
    with pytest.raises(ValueError, match="Invalid name"):
        ModelsConfig.model_validate(_cfg(providers={"bad name!": {"api_key_env": "K"}}))
    with pytest.raises(ValueError, match="empty 'model'"):
        ModelsConfig.model_validate(_cfg(models={"m1": {"provider": "p1", "model": "  "}}))


# ---------------------------------------------------------------------------
# 编译
# ---------------------------------------------------------------------------

def test_compile_fills_all_roles_from_default():
    cfg = ModelsConfig.model_validate(_cfg(
        models={"m1": {"provider": "p1", "model": "x"},
                "m2": {"provider": "p1", "model": "y"}},
        roles={"default": "m1", "extraction": "m2"},
    ))
    profiles, roles = compile_to_profiles(cfg)
    assert set(roles) == set(ROLE_NAMES)
    assert roles["extraction"] == "m2"
    assert all(roles[r] == "m1" for r in ROLE_NAMES if r != "extraction")
    assert set(profiles) == {"m1", "m2"}


def test_compile_field_mapping():
    cfg = ModelsConfig.model_validate({
        "providers": {"anth": {"protocol": "anthropic", "api_base": "https://a/v1",
                                "api_key_env": "A_KEY", "thinking_style": "enable_thinking",
                                "api_key_fallback": "ph"}},
        "models": {"m": {"provider": "anth", "model": "claude-x", "temperature": None,
                          "max_tokens": 1234, "enable_thinking": True}},
        "roles": {"default": "m"},
    })
    p = compile_to_profiles(cfg)[0]["m"]
    assert p.provider == "anthropic"          # protocol → ModelProfile.provider
    assert p.api_base == "https://a/v1"
    assert p.api_key_env == "A_KEY" and p.api_key_fallback == "ph"
    assert p.thinking_style == "enable_thinking"
    assert p.temperature is None and p.max_tokens == 1234 and p.enable_thinking is True


def test_compile_rpm_inheritance():
    cfg = ModelsConfig.model_validate({
        "providers": {"p": {"api_key_env": "K", "rpm": 90, "tpm": 1000}},
        "models": {"inherit": {"provider": "p", "model": "a"},
                    "override": {"provider": "p", "model": "b", "rpm": 5}},
        "roles": {"default": "inherit"},
    })
    profiles = compile_to_profiles(cfg)[0]
    assert profiles["inherit"].rpm == 90 and profiles["inherit"].tpm == 1000
    assert profiles["override"].rpm == 5 and profiles["override"].tpm == 1000


def test_default_template_compiles():
    cfg = default_models_config()
    profiles, roles = compile_to_profiles(cfg)
    assert roles["orchestrator"] == "strong" and roles["extraction"] == "fast"
    assert profiles["strong"].api_base == "https://openrouter.ai/api/v1"
    assert profiles["strong"].api_key_env == "OPENROUTER_API_KEY"


def test_compiled_profiles_feed_get_model_for(monkeypatch):
    """编译产物可直接喂 get_model_for（对齐 test_provider_config 烟测风格）。"""
    from searchos.config.settings import settings
    import searchos.config.models as models_mod

    profiles, roles = compile_to_profiles(default_models_config())
    monkeypatch.setattr(settings, "profiles", profiles)
    monkeypatch.setattr(settings, "roles", roles)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    llm = models_mod.get_model_for("extraction")
    assert llm.model_name == "google/gemini-3.5-flash"


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------

def test_save_load_roundtrip_atomic(tmp_path):
    path = tmp_path / "models.json"
    cfg = default_models_config()
    save_models_config(cfg, path)
    assert load_models_config(path) == cfg
    assert [p.name for p in tmp_path.iterdir()] == ["models.json"]  # 无 tmp 残留


def test_models_config_path_respects_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SF_MODELS_FILE", str(tmp_path / "elsewhere.json"))
    assert models_config_path() == tmp_path / "elsewhere.json"


def test_load_invalid_raises_with_path(tmp_path):
    path = tmp_path / "models.json"
    path.write_text("{not json")
    with pytest.raises(ModelsConfigError, match=str(path)):
        load_models_config(path)
    path.write_text('{"version": 1, "providers": {}, "models": {}, "roles": {}}')
    with pytest.raises(ModelsConfigError, match="default"):
        load_models_config(path)


def test_compiled_from_file_none_when_missing(tmp_path):
    assert compiled_from_file(tmp_path / "nope.json") is None


# ---------------------------------------------------------------------------
# check_runnable（preflight）
# ---------------------------------------------------------------------------

def test_check_runnable_reports_missing_keys(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    missing = check_runnable(default_models_config())
    assert len(missing) == 1 and "OPENROUTER_API_KEY" in missing[0]
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-x")
    assert check_runnable(default_models_config()) == []


def test_check_runnable_ignores_unused_cards(monkeypatch):
    monkeypatch.delenv("UNUSED_KEY", raising=False)
    monkeypatch.setenv("USED_KEY", "k")
    cfg = ModelsConfig.model_validate({
        "providers": {"used": {"api_key_env": "USED_KEY"},
                       "unused": {"api_key_env": "UNUSED_KEY"}},
        "models": {"m": {"provider": "used", "model": "x"},
                    "orphan": {"provider": "unused", "model": "y"}},
        "roles": {"default": "m"},
    })
    assert check_runnable(cfg) == []


def test_check_runnable_fallback_key_counts(monkeypatch):
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    cfg = ModelsConfig.model_validate({
        "providers": {"local": {"api_key_env": "OLLAMA_API_KEY", "api_key_fallback": "ollama"}},
        "models": {"m": {"provider": "local", "model": "qwen3:32b"}},
        "roles": {"default": "m"},
    })
    assert check_runnable(cfg) == []


# ---------------------------------------------------------------------------
# 遗留折叠与虚拟配置
# ---------------------------------------------------------------------------

def test_config_from_legacy_roundtrip_builtin():
    cfg = config_from_legacy(builtin_profiles(), builtin_roles())
    _, roles = compile_to_profiles(cfg)
    assert roles == builtin_roles()  # 角色解析等价
    # builtin 有两个 key env（OPENAI/SF_EXTRACTION）+ anthropic → ≥2 个 provider
    assert len(cfg.providers) >= 2
    assert set(cfg.models) == set(builtin_profiles())


def test_config_from_legacy_preset(monkeypatch):
    from searchos.config.providers import provider_default_profiles, provider_default_roles
    monkeypatch.setenv("SF_PROVIDER", "deepseek")
    for var in ("SF_MODEL", "SF_FAST_MODEL", "SF_API_BASE", "SF_API_KEY_ENV"):
        monkeypatch.delenv(var, raising=False)
    cfg = config_from_legacy(provider_default_profiles(), provider_default_roles(), "deepseek")
    assert list(cfg.providers) == ["deepseek"]  # 单一连接聚成一个 provider
    assert set(cfg.models) == {"main", "judge", "fast", "synthesis", "reformat"}
    assert cfg.roles["default"] == "main"
    _, roles = compile_to_profiles(cfg)
    assert roles == provider_default_roles()


def test_virtual_models_config_branches(monkeypatch):
    for var in ("SF_PROVIDER", "SF_MODEL", "SF_FAST_MODEL", "SF_API_BASE",
                "SF_API_KEY_ENV", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert "openrouter" in virtual_models_config().providers  # 全无 → 默认模板

    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    assert set(virtual_models_config().models) == set(builtin_profiles())  # builtin 分支

    monkeypatch.setenv("SF_PROVIDER", "deepseek")
    assert "deepseek" in virtual_models_config().providers  # 预设分支
