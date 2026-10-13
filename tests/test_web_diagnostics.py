"""Connection diagnostics and resource telemetry regression tests."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent
for path in (str(_REPO), str(_REPO / "web")):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.mark.asyncio
async def test_provider_diagnostic_reports_latency_usage_and_thinking(monkeypatch):
    from api.routes.diagnostics import ProviderTestRequest, test_provider

    import searchos.config.models as models

    profile = SimpleNamespace(
        provider="openai_compatible",
        model="test-model",
        enable_thinking=True,
        thinking_style="enable_thinking",
    )

    class FakeModel:
        async def ainvoke(self, _prompt):
            return SimpleNamespace(
                content="OK",
                additional_kwargs={"reasoning_content": "brief reasoning"},
                usage_metadata={"input_tokens": 4, "output_tokens": 1, "total_tokens": 5},
            )

    monkeypatch.setattr(models, "resolve_profile", lambda _role: profile)
    monkeypatch.setattr(models, "get_model_for", lambda _role: FakeModel())

    result = await test_provider(ProviderTestRequest(role="orchestrator"))

    assert result["ok"] is True
    assert result["model"] == "test-model"
    assert result["thinking_status"] == "observed"
    assert result["usage"]["total_tokens"] == 5
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_search_diagnostic_uses_configured_provider(monkeypatch):
    from api.routes import diagnostics
    from api.routes.diagnostics import SearchTestRequest, test_search_backend

    from searchos.tools.simple_browser.search.base import SearchResult

    search_module = import_module("searchos.tools.simple_browser.search")

    class FakeProvider:
        async def search(self, query, max_results=10):
            assert query == "diagnostic query"
            assert max_results == 3
            return [SearchResult(title="Result", url="https://example.com/page")]

    monkeypatch.setattr(diagnostics.store.models, "search_provider", "serper")
    monkeypatch.setattr(search_module, "resolve_search_provider_name", lambda _name: "serper")
    monkeypatch.setattr(search_module, "build_search_provider", lambda _name: FakeProvider())

    result = await test_search_backend(SearchTestRequest(query="diagnostic query"))

    assert result["ok"] is True
    assert result["provider"] == "serper"
    assert result["result_count"] == 1
    assert result["results"][0]["domain"] == "example.com"


@pytest.mark.asyncio
async def test_browser_diagnostic_fetches_and_redacts_proxy_credentials(monkeypatch):
    from api.routes import diagnostics
    from api.routes.diagnostics import BrowserTestRequest, test_browser_backend

    import searchos.tools.simple_browser.backend.base as backend_module
    from searchos.config.settings import settings
    from searchos.tools.simple_browser.backend.base import FetchResult

    class FakeBackend:
        closed = False

        async def fetch(self, url, *, query="", timeout=20.0):
            assert url == "https://example.com"
            return FetchResult(url=url, title="Example", markdown="content", status=200)

        async def close(self):
            self.closed = True

    fake = FakeBackend()
    monkeypatch.setattr(backend_module, "_build_default_backend", lambda: fake)
    monkeypatch.setattr(settings, "browser_backend", "aiohttp")
    monkeypatch.setattr(
        diagnostics.store.advanced,
        "https_proxy",
        "http://user:secret@127.0.0.1:7890",
    )

    result = await test_browser_backend(BrowserTestRequest(url="https://example.com"))

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["proxy"]["endpoint"] == "http://127.0.0.1:7890"
    assert "secret" not in str(result)
    assert fake.closed is True


@pytest.mark.asyncio
async def test_browser_diagnostic_rejects_private_urls(monkeypatch):
    from api.routes.diagnostics import BrowserTestRequest, test_browser_backend

    import searchos.tools.simple_browser.backend.base as backend_module

    built = False

    def build():
        nonlocal built
        built = True
        raise AssertionError("backend must not be built")

    monkeypatch.setattr(backend_module, "_build_default_backend", build)
    result = await test_browser_backend(BrowserTestRequest(url="http://127.0.0.1/admin"))

    assert result["ok"] is False
    assert "Private-network" in result["error"]
    assert built is False


def test_trajectory_logger_counts_dict_and_string_actions(tmp_path):
    from searchos.harness.telemetry.episodic import TrajectoryLogger
    from searchos.harness.telemetry.trajectory import TrajectoryStep

    logger = TrajectoryLogger(tmp_path / "trajectory.jsonl")
    logger.log_step(TrajectoryStep(timestamp="now", action="search"))
    logger._append_raw({
        "type": "step",
        "agent": "sub_agent",
        "action": {"name": "open", "args": {}},
    })

    assert logger.tool_counts == {"search": 1, "open": 1}


def test_diagnostic_routes_are_registered():
    from api.main import app

    paths = app.openapi()["paths"]
    assert "/api/diagnostics/provider" in paths
    assert "/api/diagnostics/search" in paths
    assert "/api/diagnostics/browser" in paths


def test_diagnostic_errors_redact_keys_and_proxy_credentials():
    from api.routes.diagnostics import _safe_error

    message = _safe_error(RuntimeError(
        "Bearer secret-token-value via http://user:password@proxy.local:7890 and sk-secretvalue123",
    ))

    assert "secret-token-value" not in message
    assert "user:password" not in message
    assert "sk-secretvalue123" not in message
