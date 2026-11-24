"""搜索后端工厂的解析逻辑测试（不发请求）。"""

from __future__ import annotations

import pytest

from searchos.tools.simple_browser.search import (
    build_search_provider,
    resolve_search_provider_name,
)


def _clear(monkeypatch):
    for var in ("SF_SEARCH_PROVIDER", "SERPER_API_KEY", "TAVILY_API_KEY",
                "SF_SERPER_API_KEY", "SF_TAVILY_API_KEY",
                "SPECSTREAM_API_KEY", "SF_SPECSTREAM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    # settings 单例是 import 时构造的，同样要清干净
    import searchos.config.settings as settings_mod
    monkeypatch.setattr(settings_mod.settings, "serper_api_key", "")
    monkeypatch.setattr(settings_mod.settings, "tavily_api_key", "")
    monkeypatch.setattr(settings_mod.settings, "specstream_api_key", "")


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


def test_auto_infer_specstream_from_key(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SPECSTREAM_API_KEY", "k")
    assert resolve_search_provider_name() == "specstream"
    assert build_search_provider().name == "specstream"


def test_specstream_provider_search(monkeypatch):
    import asyncio

    import httpx

    from searchos.tools.simple_browser.search.specstream import SpecStreamProvider

    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "sources": [
                        {
                            "title": "Example",
                            "url": "https://example.com",
                            "snippet": "Brief snippet",
                            "excerpt": "Detailed passage",
                        }
                    ]
                },
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    provider = SpecStreamProvider(api_key="test-key")
    rows = asyncio.run(provider.search("test query", max_results=5))
    assert captured["url"] == "https://api.specstream.ai/v1/web-search"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"] == {"q": "test query", "num": 5, "passages": True}
    assert len(rows) == 1
    assert rows[0].title == "Example"
    assert rows[0].snippet == "Brief snippet"
    assert rows[0].content == "Detailed passage"
