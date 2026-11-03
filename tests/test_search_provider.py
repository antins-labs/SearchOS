"""搜索后端工厂的解析逻辑测试（不发请求）。"""

from __future__ import annotations

import pytest

from searchos.tools.simple_browser.search import (
    build_search_provider,
    resolve_search_provider_name,
)


def _clear(monkeypatch):
    for var in ("SF_SEARCH_PROVIDER", "SERPER_API_KEY", "TAVILY_API_KEY", "KEENABLE_API_KEY",
                "SF_SERPER_API_KEY", "SF_TAVILY_API_KEY", "SF_KEENABLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    # settings 单例是 import 时构造的，同样要清干净
    import searchos.config.settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "serper_api_key", "")
    monkeypatch.setattr(settings_mod.settings, "tavily_api_key", "")
    monkeypatch.setattr(settings_mod.settings, "keenable_api_key", "")


def test_explicit_provider(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SF_SEARCH_PROVIDER", "tavily")
    assert resolve_search_provider_name() == "tavily"


def test_auto_infer_serper_from_key(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SERPER_API_KEY", "k")
    assert resolve_search_provider_name() == "serper"
    assert build_search_provider().name == "serper"


def test_auto_infer_tavily_from_key(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    assert resolve_search_provider_name() == "tavily"


def test_fallback_ragflow(monkeypatch):
    _clear(monkeypatch)
    assert resolve_search_provider_name() == "ragflow"
    assert build_search_provider().name == "ragflow"


def test_unknown_provider_raises(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SF_SEARCH_PROVIDER", "google")
    with pytest.raises(ValueError, match="serper"):
        resolve_search_provider_name()


def test_auto_infer_keenable_from_key(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("KEENABLE_API_KEY", "k")
    assert resolve_search_provider_name() == "keenable"
    assert build_search_provider().name == "keenable"


def test_serper_and_tavily_win_over_keenable(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("KEENABLE_API_KEY", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    assert resolve_search_provider_name() == "tavily"


def test_keenable_explicit_without_key_uses_public_endpoint(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SF_SEARCH_PROVIDER", "keenable")
    provider = build_search_provider()
    assert provider.name == "keenable"
    url, headers = provider._request()
    assert url == "https://api.keenable.ai/v1/search/public"
    assert headers["X-Keenable-Title"] == "SearchOS"
    assert "X-API-Key" not in headers


def test_keenable_with_key_uses_authenticated_endpoint(monkeypatch):
    _clear(monkeypatch)
    from searchos.tools.simple_browser.search.keenable import KeenableProvider

    url, headers = KeenableProvider(api_key="secret")._request()
    assert url == "https://api.keenable.ai/v1/search"
    assert headers["X-API-Key"] == "secret"
    assert "X-Keenable-Title" not in headers


def test_keenable_parse_results():
    from searchos.tools.simple_browser.search.keenable import parse_results

    results = parse_results({"results": [
        {"title": "A", "url": "https://a.example", "snippet": "sa", "description": ""},
        {"title": "", "url": "https://b.example", "snippet": "", "description": "db"},
        {"title": "no url", "url": "", "snippet": "x"},
    ]})
    assert [(r.title, r.url, r.snippet) for r in results] == [
        ("A", "https://a.example", "sa"),
        ("https://b.example", "https://b.example", "db"),
    ]
    with pytest.raises(RuntimeError):
        parse_results({"error": "bad"})
