"""searchos/config/web_overlay.py — advanced 区应用 + 遗留 env 迁移。

overlay 与 settings 都是模块级单例，用例内重置到干净态并在结束时还原，
不触碰真实 web_settings.json。
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture()
def clean_overlay(tmp_path, monkeypatch):
    """把 overlay 落盘重定向到 tmp，store/settings 重置到干净态并复原。"""
    from searchos.config import web_overlay as wo
    from searchos.config.settings import reload_settings_in_place, settings

    monkeypatch.setenv("SF_WEB_SETTINGS_PATH", str(tmp_path / "web_settings.json"))
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "SF_ENABLE_SKILLS",
                "SF_SEARCH_PROVIDER", "SF_BROWSER_DISK_CACHE_DIR"):
        monkeypatch.delenv(var, raising=False)

    env_snapshot = dict(os.environ)
    retries0 = settings.llm_max_retries
    cache0 = settings.browser_disk_cache_dir

    wo._replace_store(wo.WebSettings())
    yield wo

    os.environ.clear()
    os.environ.update(env_snapshot)
    wo._replace_store(wo.WebSettings())
    reload_settings_in_place()
    settings.llm_max_retries = retries0
    settings.browser_disk_cache_dir = cache0


def test_advanced_apply_sets_settings_and_proxy(clean_overlay):
    wo = clean_overlay
    from searchos.config.settings import settings

    wo.store.advanced.llm_max_retries = 11
    wo.store.advanced.browser_disk_cache_dir = "/tmp/sos-cache"
    wo.store.advanced.https_proxy = "http://127.0.0.1:7890"
    wo.apply_to_runtime()

    assert settings.llm_max_retries == 11
    assert settings.browser_disk_cache_dir == "/tmp/sos-cache"
    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:7890"
    assert os.environ["HTTPS_PROXY"] == "http://127.0.0.1:7890"


def test_advanced_empty_proxy_unsets_env(clean_overlay):
    wo = clean_overlay
    os.environ["HTTP_PROXY"] = "http://stale"
    os.environ["HTTPS_PROXY"] = "http://stale"
    wo.store.advanced.https_proxy = ""  # explicit no-proxy
    wo.apply_to_runtime()
    assert "HTTP_PROXY" not in os.environ
    assert "HTTPS_PROXY" not in os.environ


def test_advanced_none_leaves_env_untouched(clean_overlay):
    wo = clean_overlay
    os.environ["HTTPS_PROXY"] = "http://keep"
    wo.store.advanced.https_proxy = None  # no override
    wo.apply_to_runtime()
    assert os.environ["HTTPS_PROXY"] == "http://keep"


def test_migrate_seeds_overlay_from_env(clean_overlay, monkeypatch):
    wo = clean_overlay
    monkeypatch.setenv("SF_ENABLE_SKILLS", "false")
    monkeypatch.setenv("SF_ENABLE_EXPLORE_BATCH", "false")
    monkeypatch.setenv("SF_SEARCH_PROVIDER", "serper")
    monkeypatch.setenv("SF_BROWSER_DISK_CACHE_DIR", "/tmp/pc")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1080")

    seeded = wo.migrate_legacy_env_into_overlay()

    assert wo.store.run_defaults.enable_skills is False
    assert wo.store.run_defaults.enable_explore_batch is False
    assert wo.store.models.search_provider == "serper"
    assert wo.store.advanced.browser_disk_cache_dir == "/tmp/pc"
    assert wo.store.advanced.https_proxy == "http://127.0.0.1:1080"
    assert "SF_ENABLE_SKILLS" in seeded and "SF_SEARCH_PROVIDER" in seeded
    assert "SF_ENABLE_EXPLORE_BATCH" in seeded


def test_migrate_is_idempotent(clean_overlay, monkeypatch):
    wo = clean_overlay
    monkeypatch.setenv("SF_SEARCH_PROVIDER", "tavily")
    assert wo.migrate_legacy_env_into_overlay()  # first run seeds
    assert wo.migrate_legacy_env_into_overlay() == []  # nothing left to seed


def test_migrate_does_not_override_existing_overlay(clean_overlay, monkeypatch):
    wo = clean_overlay
    wo.store.models.search_provider = "serper"  # user already chose
    monkeypatch.setenv("SF_SEARCH_PROVIDER", "tavily")
    wo.migrate_legacy_env_into_overlay()
    assert wo.store.models.search_provider == "serper"  # overlay wins, unchanged
