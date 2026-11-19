"""Exercise the native search tool and capture actual HTTP requests."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from threading import Thread

import pytest

from searchos.cli import _setup_provider
from searchos.config.settings import settings
from searchos.config.web_overlay import store
from searchos.tools.simple_browser import search, state
from searchos.tools.simple_browser.search.parallel import ParallelProvider


@pytest.fixture
def parallel_endpoint(monkeypatch):
    requests = []
    tool_replies = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            message = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, dict(self.headers), message))
            method = message["method"]
            if method == "notifications/initialized":
                self.send_response(202)
                self.end_headers()
                return
            if method == "initialize":
                response = {"result": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "Search fixture", "version": "1"},
                }}
                status, content_type = 200, "application/json"
            elif method == "tools/list":
                response = {"result": {"tools": [{
                    "name": "web_search",
                    "inputSchema": {"type": "object"},
                }]}}
                status, content_type = 200, "application/json"
            else:
                assert method == "tools/call"
                status, content_type, response = tool_replies.pop(0)

            payload = json.dumps({"jsonrpc": "2.0", "id": message["id"], **response}).encode()
            if content_type == "text/event-stream":
                payload = b"event: message\ndata: " + payload + b"\n\n"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            if method == "initialize":
                self.send_header("Set-Cookie", "visitor=fixture-id; Path=/mcp")
            if status == 307:
                self.send_header("Location", "/other?visitor=fixture-id")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        monkeypatch.setattr(ParallelProvider, "ENDPOINT", f"http://127.0.0.1:{server.server_port}/mcp")
        monkeypatch.setenv("NO_PROXY", "127.0.0.1")
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield requests, tool_replies
        finally:
            server.shutdown()
            thread.join()


@pytest.mark.asyncio
async def test_cli_search_uses_anonymous_parallel_only_when_selected(
    parallel_endpoint, monkeypatch,
):
    requests, replies = parallel_endpoint
    monkeypatch.setattr(store.models, "search_provider", None)
    monkeypatch.setattr(state, "_provider", None)
    monkeypatch.setattr(settings, "serper_api_key", "")
    monkeypatch.setattr(settings, "tavily_api_key", "")
    for name in ("SF_SEARCH_PROVIDER", "SERPER_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    _setup_provider(no_search=False)
    assert state.get_provider().name == "ragflow"
    monkeypatch.setenv("SERPER_API_KEY", "example")
    _setup_provider(no_search=False)
    assert state.get_provider().name == "serper"
    monkeypatch.setenv("SF_SEARCH_PROVIDER", "parallel")
    _setup_provider(no_search=True)
    assert state.get_provider().name == "serper"
    assert requests == []

    monkeypatch.setattr(settings, "search_max_results", 1)
    _setup_provider(no_search=False)
    assert state.get_provider().name == "parallel"
    source = "https://science.nasa.gov/mission/webb/?ref=original#first-images"
    hits = [
        {"url": source, "title": "Webb", "excerpts": ["Webb's first deep field."]},
        {"url": "https://example.com/other", "title": "Other", "excerpts": ["Other result"]},
    ]
    for content_type in ("text/event-stream", "application/json"):
        replies.append((200, content_type, {
            "result": {"content": [], "structuredContent": {"results": hits}},
        }))
        state.reset_browser()
        rendered = await search.ainvoke({"query": "Webb first deep field"})
        assert source in rendered
        assert "Webb's first deep field." in rendered
        assert "1 results" in rendered
        assert "example.com/other" not in rendered

    methods = [message["method"] for _, _, message in requests]
    assert methods == ["initialize", "notifications/initialized", "tools/list", "tools/call"] * 2
    for path, headers, message in requests:
        headers = {name.lower(): value for name, value in headers.items()}
        assert path == "/mcp"
        assert headers["user-agent"] == f"SearchOS/{version('searchos')}"
        assert {"authorization", "x-api-key", "cookie"}.isdisjoint(headers)
        if message["method"] == "tools/call":
            assert message["params"] == {
                "name": "web_search",
                "arguments": {
                    "objective": "Webb first deep field",
                    "search_queries": ["Webb first deep field"],
                },
            }


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "reply", "error"), [
    (429, {}, "request failed"),
    (200, {"error": {"code": -32000, "message": "Service unavailable"}}, "request failed"),
    (200, {"result": {"isError": True, "content": []}}, "returned a tool error"),
    (200, {"result": {"content": [], "structuredContent": {}}}, "returned invalid results"),
])
async def test_parallel_failures_do_not_become_empty_results(
    parallel_endpoint, status, reply, error,
):
    _, replies = parallel_endpoint
    replies.append((status, "application/json", reply))
    with pytest.raises(RuntimeError, match=error):
        await ParallelProvider().search("Webb first deep field")


@pytest.mark.asyncio
async def test_parallel_does_not_follow_same_origin_redirect(parallel_endpoint):
    requests, replies = parallel_endpoint
    replies.extend([
        (307, "application/json", {}),
        (200, "application/json", {
            "result": {"content": [], "structuredContent": {"results": []}},
        }),
    ])
    with pytest.raises(RuntimeError, match="request failed"):
        await ParallelProvider().search("Webb first deep field")
    assert all(path == "/mcp" for path, _, _ in requests)
