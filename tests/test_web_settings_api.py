"""Web 设置 API — provider 切换 / key 写入 / 聚合视图形状的回归测试。

全部走 TestClient；.env 与 web_settings.json 均重定向到 tmp_path，
绝不触碰真实配置文件。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for p in (str(_REPO), str(_REPO / "web")):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with .env / overlay redirected to tmp and a clean env."""
    import api.deps as deps
    import api.settings_store as settings_store
    from searchos.config.providers import PRESETS
    from searchos.config.settings import reload_settings_in_place

    for var in ("SF_PROVIDER", "SF_MODEL", "SF_FAST_MODEL", "SF_API_BASE",
                "SF_API_KEY_ENV", "SF_BUILTIN_OPENAI_BASE", "SF_BUILTIN_ANTHROPIC_BASE"):
        monkeypatch.delenv(var, raising=False)
    for preset in PRESETS.values():
        monkeypatch.delenv(preset.api_key_env, raising=False)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    monkeypatch.setattr(deps, "ENV_FILE_PATH", str(tmp_path / ".env"))
    monkeypatch.setattr(settings_store, "WEB_SETTINGS_PATH", str(tmp_path / "web_settings.json"))

    from fastapi.testclient import TestClient
    from api.main import app

    import os
    env_snapshot = dict(os.environ)

    with TestClient(app) as c:
        yield c, tmp_path

    # 还原：update_env 会直接改 os.environ（monkeypatch 不知情），整体回滚
    # 到进入测试时的快照，再把 settings 单例和 overlay 恢复干净。
    os.environ.clear()
    os.environ.update(env_snapshot)
    settings_store.reset()


def _env_text(tmp_path) -> str:
    env = tmp_path / ".env"
    return env.read_text() if env.exists() else ""


# ---------------------------------------------------------------------------
# GET /providers
# ---------------------------------------------------------------------------

def test_providers_list_complete_and_secret_free(client):
    c, _ = client
    from searchos.config.providers import PRESETS

    r = c.get("/api/settings/providers")
    assert r.status_code == 200
    data = r.json()
    listed = [p["name"] for g in data["groups"] for p in g["presets"]]
    assert sorted(listed) == sorted(PRESETS)
    assert data["active"] == ""
    sample = data["groups"][0]["presets"][0]
    assert set(sample) >= {"name", "label", "api_key_env", "requires_key",
                           "requires_model", "key_set", "doc_url"}
    assert "api_key" not in sample and "value" not in sample


# ---------------------------------------------------------------------------
# PUT /provider
# ---------------------------------------------------------------------------

def test_switch_provider_writes_env_and_rebuilds_profiles(client):
    c, tmp_path = client
    r = c.put("/api/settings/provider",
              json={"preset": "deepseek", "api_key": "sk-test-123"})
    assert r.status_code == 200, r.text
    text = _env_text(tmp_path)
    assert "SF_PROVIDER=deepseek" in text
    assert "DEEPSEEK_API_KEY=sk-test-123" in text
    models = r.json()["models"]
    assert set(models["profiles"]) == {"main", "judge", "fast", "synthesis", "reformat"}
    assert models["active_provider_preset"] == "deepseek"
    # 密钥绝不回显
    assert "sk-test-123" not in r.text.replace("DEEPSEEK_API_KEY=sk-test-123", "")
    assert "sk-test-123" not in c.get("/api/settings").text


def test_switch_requires_key(client):
    c, _ = client
    r = c.put("/api/settings/provider", json={"preset": "deepseek"})
    assert r.status_code == 400
    assert "DEEPSEEK_API_KEY" in r.json()["detail"]


def test_local_preset_requires_model_but_no_key(client):
    c, tmp_path = client
    r = c.put("/api/settings/provider", json={"preset": "ollama"})
    assert r.status_code == 400  # 缺 model
    r = c.put("/api/settings/provider", json={"preset": "ollama", "model": "qwen3:32b"})
    assert r.status_code == 200, r.text
    assert "SF_MODEL=qwen3:32b" in _env_text(tmp_path)


def test_unknown_preset_400(client):
    c, _ = client
    r = c.put("/api/settings/provider", json={"preset": "nope"})
    assert r.status_code == 400


def test_switch_clears_role_overrides_and_stale_model_override(client):
    c, tmp_path = client
    c.put("/api/settings/provider", json={"preset": "ollama", "model": "qwen3:32b"})
    # 造一个 role override（ollama 预设的 profile 名为 main/judge/...）
    r = c.put("/api/settings/models/roles", json={"roles": {"judge": "main"}})
    assert r.status_code == 200
    r = c.put("/api/settings/provider", json={"preset": "deepseek", "api_key": "sk-x"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cleared_role_overrides"] == ["judge"]
    assert any("SF_MODEL" in w for w in body["warnings"])  # 旧 model 覆写被清
    import os
    assert not os.environ.get("SF_MODEL")
    assert body["models"]["role_overrides"] == {}


def test_switch_preserves_effort_level(client):
    c, _ = client
    r = c.put("/api/settings/effort", json={"level": "high"})
    assert r.status_code == 200
    c.put("/api/settings/provider", json={"preset": "ollama", "model": "qwen3:32b"})
    r = c.get("/api/settings")
    effort = r.json()["effort"]
    assert effort["level"] == "high"
    assert effort["knobs"]["orch_max_iterations"] == 100  # reload 后 overlay 已重放


def test_repeated_switch_keeps_single_env_line(client):
    c, tmp_path = client
    c.put("/api/settings/provider", json={"preset": "deepseek", "api_key": "sk-1"})
    c.put("/api/settings/provider", json={"preset": "openai", "api_key": "sk-2"})
    lines = [l for l in _env_text(tmp_path).splitlines() if l.startswith("SF_PROVIDER=")]
    assert lines == ["SF_PROVIDER=openai"]


def test_injection_value_rejected_before_disk(client):
    c, tmp_path = client
    r = c.put("/api/settings/provider",
              json={"preset": "deepseek", "api_key": "sk\nSF_EVIL=1"})
    assert r.status_code == 400
    assert "SF_EVIL" not in _env_text(tmp_path)


# ---------------------------------------------------------------------------
# PUT /keys
# ---------------------------------------------------------------------------

def test_put_key_allowlisted(client):
    c, tmp_path = client
    r = c.put("/api/settings/keys", json={"env": "SERPER_API_KEY", "value": "serp-1"})
    assert r.status_code == 200, r.text
    assert "SERPER_API_KEY=serp-1" in _env_text(tmp_path)
    serper = next(p for p in r.json()["search"]["providers"] if p["name"] == "serper")
    assert serper["key_set"] is True
    assert "serp-1" not in r.text


def test_put_key_rejects_arbitrary_env(client):
    c, tmp_path = client
    for env in ("PATH", "SF_PROVIDER", "SF_MODEL", "EVIL_VAR"):
        r = c.put("/api/settings/keys", json={"env": env, "value": "x"})
        assert r.status_code == 400, env
    assert _env_text(tmp_path) == ""


def test_put_key_rejects_bad_value(client):
    c, _ = client
    r = c.put("/api/settings/keys", json={"env": "SERPER_API_KEY", "value": "a\nb"})
    assert r.status_code == 400


def test_put_key_clear(client):
    c, tmp_path = client
    c.put("/api/settings/keys", json={"env": "SERPER_API_KEY", "value": "serp-1"})
    r = c.put("/api/settings/keys", json={"env": "SERPER_API_KEY", "value": ""})
    assert r.status_code == 200
    assert "SERPER_API_KEY=\n" in _env_text(tmp_path)
    import os
    assert "SERPER_API_KEY" not in os.environ


# ---------------------------------------------------------------------------
# 聚合视图形状（前端兼容）
# ---------------------------------------------------------------------------

def test_aggregate_shape_unchanged(client):
    c, _ = client
    d = c.get("/api/settings").json()
    assert set(d) == {"effort", "skills", "models", "run_defaults"}
    assert set(d["effort"]) == {"level", "knobs", "overrides", "levels"}
    assert set(d["models"]) >= {"active_provider_preset", "profiles", "roles",
                                "role_overrides", "search", "browser_backend"}
    assert set(d["run_defaults"]) == {"max_time_s", "search_max_results", "enable_skills"}


# ---------------------------------------------------------------------------
# Profile 编辑 / 自定义 profile
# ---------------------------------------------------------------------------

def test_patch_base_profile_override_and_clear(client):
    c, _ = client
    c.put("/api/settings/provider", json={"preset": "ollama", "model": "qwen3:32b"})
    r = c.patch("/api/settings/profiles/main", json={"api_base": "http://gpu-box:8000/v1"})
    assert r.status_code == 200, r.text
    p = r.json()["profiles"]["main"]
    assert p["api_base"] == "http://gpu-box:8000/v1"
    assert p["overridden"] == ["api_base"]
    assert p["custom"] is False
    # "" 清除覆写 → 回到预设 base
    r = c.patch("/api/settings/profiles/main", json={"api_base": ""})
    p = r.json()["profiles"]["main"]
    assert p["api_base"] == "http://localhost:11434/v1"
    assert p["overridden"] == []


def test_patch_unknown_profile_404(client):
    c, _ = client
    r = c.patch("/api/settings/profiles/nope", json={"model": "x"})
    assert r.status_code == 404


def test_custom_profile_lifecycle(client):
    c, _ = client
    body = {"name": "my-vllm", "model": "Qwen3-32B", "api_base": "http://localhost:8000/v1",
            "api_key_env": "MY_VLLM_KEY"}
    r = c.post("/api/settings/profiles", json=body)
    assert r.status_code == 200, r.text
    p = r.json()["profiles"]["my-vllm"]
    assert p["custom"] is True and p["model"] == "Qwen3-32B"

    # 自定义 profile 的 key env 自动进白名单
    r = c.put("/api/settings/keys", json={"env": "MY_VLLM_KEY", "value": "vk-1"})
    assert r.status_code == 200, r.text
    assert r.json()["profiles"]["my-vllm"]["api_key_set"] is True

    # 绑定角色后不可删
    r = c.put("/api/settings/models/roles", json={"roles": {"judge": "my-vllm"}})
    assert r.status_code == 200
    r = c.delete("/api/settings/profiles/my-vllm")
    assert r.status_code == 400
    assert "judge" in r.json()["detail"]

    # 编辑自定义 profile 是直接改（非覆写）
    r = c.patch("/api/settings/profiles/my-vllm", json={"model": "Qwen3-72B"})
    assert r.json()["profiles"]["my-vllm"]["model"] == "Qwen3-72B"
    assert r.json()["profiles"]["my-vllm"]["overridden"] == []
    r = c.patch("/api/settings/profiles/my-vllm", json={"model": ""})
    assert r.status_code == 400  # 自定义 profile 的 model 不可置空

    # 换绑后可删
    profiles = c.get("/api/settings/models").json()["profiles"]
    fallback = next(n for n in profiles if n != "my-vllm")
    c.put("/api/settings/models/roles", json={"roles": {"judge": fallback}})
    r = c.delete("/api/settings/profiles/my-vllm")
    assert r.status_code == 200, r.text
    assert "my-vllm" not in r.json()["profiles"]


def test_create_profile_validation(client):
    c, _ = client
    base = {"model": "m", "api_key_env": "SOME_KEY"}
    assert c.post("/api/settings/profiles", json={**base, "name": "main"}).status_code == 400
    assert c.post("/api/settings/profiles", json={**base, "name": "bad name!"}).status_code == 400
    assert c.post("/api/settings/profiles",
                  json={"name": "x", "model": "m", "api_key_env": "lower_case"}).status_code == 400
    existing = next(iter(c.get("/api/settings/models").json()["profiles"]))
    assert c.post("/api/settings/profiles", json={**base, "name": existing}).status_code == 400


def test_provider_switch_clears_overrides_keeps_custom(client):
    c, _ = client
    c.put("/api/settings/provider", json={"preset": "ollama", "model": "qwen3:32b"})
    c.patch("/api/settings/profiles/main", json={"api_base": "http://gpu-box:8000/v1"})
    c.post("/api/settings/profiles", json={
        "name": "my-vllm", "model": "Qwen3-32B", "api_key_env": "MY_VLLM_KEY"})
    r = c.put("/api/settings/provider", json={"preset": "deepseek", "api_key": "sk-x"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cleared_profile_overrides"] == ["main"]
    profiles = body["models"]["profiles"]
    assert profiles["main"]["api_base"] == "https://api.deepseek.com"  # 覆写已清
    assert "my-vllm" in profiles and profiles["my-vllm"]["custom"] is True  # 自定义保留
