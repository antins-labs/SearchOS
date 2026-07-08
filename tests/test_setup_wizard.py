"""首次运行配置向导的回归测试（不发请求、不真实交互）。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from searchos.config.providers import PRESET_GROUPS
from searchos.config.setup_wizard import (
    model_config_ready,
    run_setup_wizard,
    update_env_file,
)


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

def _script_prompts(monkeypatch, answers: list[str]) -> None:
    import rich.prompt

    seq = iter(answers)

    def fake_ask(*args, **kwargs):
        val = next(seq)
        if val == "" and "default" in kwargs:
            return kwargs["default"]
        return val

    monkeypatch.setattr(rich.prompt.Prompt, "ask", staticmethod(fake_ask))


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


def test_wizard_coding_plan_flow(monkeypatch, tmp_path: Path):
    _sentinel_env(monkeypatch, "SF_PROVIDER", "ZHIPU_API_KEY")
    env = tmp_path / ".env"
    # 选 zhipu-coding → key → 模型用默认 → 端点用默认 → 跳过搜索配置
    _script_prompts(monkeypatch, [_preset_number("zhipu-coding"), "sk-real", "", "", "0"])
    assert run_setup_wizard(env)
    text = env.read_text()
    assert "SF_PROVIDER=zhipu-coding" in text
    assert "ZHIPU_API_KEY=sk-real" in text
    assert "SF_MODEL" not in text      # 默认模型不落盘
    assert "SF_API_BASE" not in text   # 默认端点不落盘
    assert "SF_SEARCH_PROVIDER" not in text  # 跳过则不写
    assert os.environ["SF_PROVIDER"] == "zhipu-coding"
    assert os.environ["ZHIPU_API_KEY"] == "sk-real"


def test_wizard_local_flow_with_search(monkeypatch, tmp_path: Path):
    _sentinel_env(monkeypatch, "SF_PROVIDER", "SF_MODEL", "SF_API_BASE")
    env = tmp_path / ".env"
    # 选 ollama → 模型名（先空后有效）→ 自定义端口 → 选 serper → 填搜索 key
    _script_prompts(monkeypatch, [
        _preset_number("ollama"), "", "qwen3:32b", "http://localhost:11500/v1",
        "1", "serper-key",
    ])
    assert run_setup_wizard(env)
    text = env.read_text()
    assert "SF_PROVIDER=ollama" in text
    assert "SF_MODEL=qwen3:32b" in text
    assert "SF_API_BASE=http://localhost:11500/v1" in text
    assert "SF_SEARCH_PROVIDER=serper" in text
    assert "SERPER_API_KEY=serper-key" in text
    assert "OLLAMA_API_KEY" not in text  # 本地部署不写模型 key


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
