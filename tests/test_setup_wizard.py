"""首次运行配置向导的回归测试（不发请求、不真实交互）。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from searchos.config.providers import PRESET_GROUPS, PRESETS
from searchos.config.setup_wizard import (
    model_config_ready,
    run_setup_wizard,
    update_env_file,
)


@pytest.fixture(autouse=True)
def _isolate_overlay(tmp_path, monkeypatch):
    """Point the web-overlay path at a per-test tmp file so model_config_ready /
    the wizard never read or write the repo's real web_settings.json."""
    monkeypatch.setenv("SF_WEB_SETTINGS_PATH", str(tmp_path / "wizard_overlay.json"))


def _preset_number(name: str) -> str:
    """向导菜单里某预设的编号（与 PRESET_GROUPS 展示顺序一致）。"""
    flat = [n for _, names in PRESET_GROUPS for n in names]
    return str(flat.index(name) + 1)


# ---------------------------------------------------------------------------
# model_config_ready
# ---------------------------------------------------------------------------

def _clear_env(monkeypatch):
    for var in ("SF_PROVIDER", "SF_MODEL", "SF_API_KEY_ENV", "OPENAI_API_KEY",
                "ZHIPU_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_ready_builtin_defaults(monkeypatch):
    _clear_env(monkeypatch)
    assert not model_config_ready()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    assert model_config_ready()


def test_ready_provider_needs_key(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SF_PROVIDER", "zhipu-coding")
    assert not model_config_ready()
    monkeypatch.setenv("ZHIPU_API_KEY", "sk-x")
    assert model_config_ready()


def test_ready_local_needs_model_but_no_key(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SF_PROVIDER", "ollama")
    assert not model_config_ready()  # 缺 SF_MODEL
    monkeypatch.setenv("SF_MODEL", "qwen3:32b")
    assert model_config_ready()  # 占位 key 自动补


def test_ready_unknown_provider(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SF_PROVIDER", "nope")
    assert not model_config_ready()


# ---------------------------------------------------------------------------
# update_env_file
# ---------------------------------------------------------------------------

def test_update_env_file_replaces_and_appends(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("# comment\nOPENAI_API_KEY=old\nSF_JINA_API_KEY=j\n")
    update_env_file(env, {"OPENAI_API_KEY": "new", "SF_PROVIDER": "deepseek"})
    text = env.read_text()
    assert "OPENAI_API_KEY=new" in text
    assert "OPENAI_API_KEY=old" not in text
    assert "SF_JINA_API_KEY=j" in text          # 无关行保留
    assert "SF_PROVIDER=deepseek" in text        # 新键追加
    assert text.index("# comment") < text.index("OPENAI_API_KEY=new")


def test_update_env_file_creates_missing(tmp_path: Path):
    env = tmp_path / ".env"
    update_env_file(env, {"SF_PROVIDER": "ollama"})
    assert env.read_text().endswith("SF_PROVIDER=ollama\n")


# ---------------------------------------------------------------------------
# run_setup_wizard（脚本化交互）
# ---------------------------------------------------------------------------

def _script(monkeypatch, prompts: list[str], confirms: list[bool]) -> None:
    """Drive the wizard's rich Prompt.ask (text) and Confirm.ask (yes/no).

    An empty answer with a non-None default returns that default (mirrors a bare
    Enter); a None default (e.g. a required model id) returns "" so the wizard's
    own "cannot be empty" loop re-asks.
    """
    import rich.prompt

    pit, cit = iter(prompts), iter(confirms)

    def fake_ask(*args, **kwargs):
        val = next(pit)
        if val == "" and kwargs.get("default") is not None:
            return kwargs["default"]
        return val

    monkeypatch.setattr(rich.prompt.Prompt, "ask", staticmethod(fake_ask))
    monkeypatch.setattr(rich.prompt.Confirm, "ask", staticmethod(lambda *a, **k: next(cit)))


def _sentinel_env(monkeypatch, *keys: str) -> None:
    """预置 sentinel 让 teardown 恢复 os.environ 到测试前状态。

    搜索相关 key 需要「运行时不存在」（决定向导分支）且 teardown 可清理：
    先 setenv 注册 undo，再 delenv 使其当下不存在。
    """
    for k in keys:
        monkeypatch.setenv(k, "sentinel")
    for k in ("SERPER_API_KEY", "TAVILY_API_KEY", "SF_SEARCH_PROVIDER"):
        monkeypatch.setenv(k, "tmp")
        monkeypatch.delenv(k)


def _read_overlay():
    from searchos.config.web_overlay import WebSettings, overlay_path
    return WebSettings.model_validate_json(overlay_path().read_text())


def _thinking_asked(preset) -> bool:
    return preset.thinking_style != "none" and preset.provider != "anthropic"


def test_wizard_coding_plan_flow(monkeypatch, tmp_path: Path):
    """选 zhipu-coding → 建连接 + 一张模型卡 → 全绑角色 → 跳过搜索。
    连接/卡/角色写 overlay；key 值写 .env；不再写 SF_PROVIDER/SF_MODEL。"""
    from searchos.config.profiles import ROLE_NAMES
    _sentinel_env(monkeypatch, "SF_PROVIDER", "ZHIPU_API_KEY")
    env = tmp_path / ".env"
    preset = PRESETS["zhipu-coding"]

    # 编号, 连接名(默认), api_base(默认), key_env(默认), [key 值], 卡名, model id(默认), temp, 搜索
    prompts = [_preset_number("zhipu-coding"), "", "", ""]
    if not preset.api_key_fallback:
        prompts.append("sk-real")
    prompts += ["", "", "", "0"]
    confirms = [False] + ([False] if _thinking_asked(preset) else []) + [False]
    _script(monkeypatch, prompts, confirms)

    assert run_setup_wizard(env)
    ov = _read_overlay()
    conn = ov.models.provider_connections["zhipu-coding"]
    assert conn.api_key_envs == ["ZHIPU_API_KEY"] and conn.protocol == preset.provider
    card = ov.models.custom_profiles["main"]
    assert card.model == preset.main_model and card.provider_ref == "zhipu-coding"
    assert all(ov.models.roles[r] == "main" for r in ROLE_NAMES)

    text = env.read_text()
    assert "SF_PROVIDER" not in text and "SF_MODEL" not in text  # 模型配置在 overlay
    assert "SF_SEARCH_PROVIDER" not in text                      # 跳过则不写
    if not preset.api_key_fallback:
        assert "ZHIPU_API_KEY=sk-real" in text
        assert os.environ["ZHIPU_API_KEY"] == "sk-real"


def test_wizard_local_flow_with_search(monkeypatch, tmp_path: Path):
    """选 ollama（本地，无需 key）→ 模型名先空后有效 → 自定义端口 → 选 serper 填 key。"""
    from searchos.config.profiles import ROLE_NAMES
    _sentinel_env(monkeypatch, "SF_PROVIDER")
    env = tmp_path / ".env"
    preset = PRESETS["ollama"]

    prompts = [_preset_number("ollama"), "", "http://localhost:11500/v1", ""]
    if not preset.api_key_fallback:
        prompts.append("ollama-key")
    prompts += ["", "", "qwen3:32b", ""]   # 卡名, model id(空重试), model id, temp
    prompts += ["1", "serper-key"]          # 搜索：serper + key
    confirms = [False] + ([False] if _thinking_asked(preset) else []) + [False]
    _script(monkeypatch, prompts, confirms)

    assert run_setup_wizard(env)
    ov = _read_overlay()
    conn = ov.models.provider_connections["ollama"]
    assert conn.api_base == "http://localhost:11500/v1"
    card = ov.models.custom_profiles["main"]
    assert card.model == "qwen3:32b" and card.provider_ref == "ollama"
    assert all(ov.models.roles[r] == "main" for r in ROLE_NAMES)
    # 搜索后端现写入 overlay（与 web/CLI/TUI 同源），只有 key 值落 .env。
    assert ov.models.search_provider == "serper"

    text = env.read_text()
    assert "SF_SEARCH_PROVIDER" not in text
    assert "SERPER_API_KEY=serper-key" in text
    assert "SF_PROVIDER" not in text and "SF_MODEL" not in text


# ---------------------------------------------------------------------------
# import 惰性：向导 import 不得触发 settings 单例构造
# ---------------------------------------------------------------------------

def test_wizard_import_does_not_construct_settings():
    code = (
        "import sys, searchos.config.setup_wizard;"
        "assert 'searchos.config.settings' not in sys.modules, 'settings imported too early'"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
