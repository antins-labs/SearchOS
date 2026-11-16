"""Runtime connection diagnostics for models, search, and browser backends."""

from __future__ import annotations

import asyncio
from functools import wraps
import ipaddress
import re
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.settings.store import store

router = APIRouter(prefix="/api/diagnostics")


def _network_scope(function):
    """一次诊断固定配置快照，并在结束时释放本地监听。"""
    @wraps(function)
    async def wrapped(*args, **kwargs):
        from searchos.network import network_context
        with network_context(reuse=False):
            return await function(*args, **kwargs)
    return wrapped


class ProviderTestRequest(BaseModel, extra="forbid"):
    role: str = "orchestrator"
    timeout_s: float = Field(default=30.0, ge=5.0, le=60.0)


class SearchTestRequest(BaseModel, extra="forbid"):
    query: str = Field(default="SearchOS agentic research", min_length=1, max_length=200)
    timeout_s: float = Field(default=20.0, ge=5.0, le=60.0)


class BrowserTestRequest(BaseModel, extra="forbid"):
    url: str = Field(default="https://example.com", min_length=8, max_length=2048)
    timeout_s: float = Field(default=20.0, ge=5.0, le=60.0)


def _safe_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    message = re.sub(r"(?:sk|key|token)-[A-Za-z0-9_-]{8,}", "[redacted]", message)
    message = re.sub(r"(https?://)[^/@\s]+@", r"\1[redacted]@", message)
    message = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]+", r"\1[redacted]", message)
    return f"{exc.__class__.__name__}: {message}"[:500]


def _response_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, list):
        return " ".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return str(content or "").strip()


def _thinking_observed(response: Any) -> bool:
    extras = getattr(response, "additional_kwargs", None) or {}
    if extras.get("reasoning_content"):
        return True
    content = getattr(response, "content", None)
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") in {"thinking", "reasoning"}
        for block in content
    )


@router.post("/provider")
@_network_scope
async def test_provider(req: ProviderTestRequest):
    """Send a minimal request through the model bound to one runtime role."""
    from searchos.config.models import get_model_for, resolve_profile

    started = perf_counter()
    try:
        profile = resolve_profile(req.role)
        model = get_model_for(req.role)
        response = await asyncio.wait_for(
            model.ainvoke("""Reply with exactly: OK"""),
            timeout=req.timeout_s,
        )
        latency_ms = round((perf_counter() - started) * 1000)
        thinking_observed = _thinking_observed(response)
        if not profile.enable_thinking:
            thinking_status = "not_requested"
        elif profile.thinking_style == "none":
            thinking_status = "not_configured"
        elif thinking_observed:
            thinking_status = "observed"
        else:
            thinking_status = "accepted"
        usage = getattr(response, "usage_metadata", None) or {}
        return {
            "ok": True,
            "kind": "provider",
            "role": req.role,
            "provider": profile.provider,
            "model": profile.model,
            "latency_ms": latency_ms,
            "thinking_enabled": profile.enable_thinking,
            "thinking_style": profile.thinking_style,
            "thinking_status": thinking_status,
            "response_preview": _response_text(response)[:120],
            "usage": {
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "kind": "provider",
            "role": req.role,
            "latency_ms": round((perf_counter() - started) * 1000),
            "error": _safe_error(exc),
        }


@router.post("/search")
@_network_scope
async def test_search_backend(req: SearchTestRequest):
    """Run a small real query through the configured search provider."""
    from searchos.tools.simple_browser.search_providers import (
        build_search_provider,
        resolve_search_provider_name,
    )

    started = perf_counter()
    configured = store.models.search_provider or ""
    try:
        provider_name = resolve_search_provider_name(configured)
        provider = build_search_provider(configured)
        results = await asyncio.wait_for(
            provider.search(req.query.strip(), max_results=3),
            timeout=req.timeout_s,
        )
        return {
            "ok": bool(results),
            "kind": "search",
            "provider": provider_name,
            "latency_ms": round((perf_counter() - started) * 1000),
            "result_count": len(results),
            "results": [
                {
                    "title": result.title[:120],
                    "domain": urlparse(result.url).netloc,
                }
                for result in results[:3]
            ],
            "error": "Search completed but returned no results" if not results else None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "kind": "search",
            "provider": configured or "auto",
            "latency_ms": round((perf_counter() - started) * 1000),
            "error": _safe_error(exc),
        }


def _validate_public_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")
    host = parsed.hostname.casefold()
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("Localhost URLs are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (address.is_private or address.is_loopback or address.is_link_local):
        raise ValueError("Private-network URLs are not allowed")
    return raw_url.strip()


def _proxy_summary() -> dict[str, Any]:
    from searchos.network import current_context
    raw = current_context().config.snapshot()["proxy_url"]
    if not raw:
        return {"configured": False, "endpoint": "Direct connection"}
    parsed = urlparse(raw)
    host = parsed.hostname or "configured proxy"
    endpoint = f"{parsed.scheme or 'proxy'}://{host}"
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port:
        endpoint += f":{port}"
    return {"configured": True, "endpoint": endpoint}


@router.post("/network")
@_network_scope
async def test_network(req: BrowserTestRequest):
    from searchos.network import network_check

    try:
        url = _validate_public_url(req.url)
        return await asyncio.wait_for(network_check(url), timeout=req.timeout_s)
    except Exception as exc:
        return {"ok": False, "error": _safe_error(exc)}


@router.get("/network/routes")
async def get_network_routes():
    from searchos.network import learned_routes
    return {"routes": learned_routes()}


@router.delete("/network/routes")
async def delete_network_routes(host: str | None = None):
    from searchos.network import clear_learned_routes, learned_routes
    clear_learned_routes(host)
    return {"routes": learned_routes()}


@router.post("/browser")
@_network_scope
async def test_browser_backend(req: BrowserTestRequest):
    """Fetch one public URL through the configured page backend and proxy."""
    from searchos.config.settings import settings
    from searchos.tools.simple_browser.fetchers.base import _build_default_backend

    started = perf_counter()
    backend = None
    try:
        url = _validate_public_url(req.url)
        backend = _build_default_backend()
        result = await asyncio.wait_for(
            backend.fetch(url, query="SearchOS connection test", timeout=req.timeout_s),
            timeout=req.timeout_s + 1,
        )
        return {
            "ok": result.ok,
            "kind": "browser",
            "backend": settings.browser_backend,
            "implementation": backend.__class__.__name__,
            "latency_ms": round((perf_counter() - started) * 1000),
            "status_code": result.status,
            "title": result.title[:160],
            "content_chars": len(result.markdown or result.html),
            "proxy": _proxy_summary(),
            "error": result.error or (
                None if result.ok else f"Fetch returned status {result.status}"
            ),
        }
    except Exception as exc:
        return {
            "ok": False,
            "kind": "browser",
            "backend": getattr(settings, "browser_backend", "unknown"),
            "latency_ms": round((perf_counter() - started) * 1000),
            "proxy": _proxy_summary(),
            "error": _safe_error(exc),
        }
    finally:
        if backend is not None:
            try:
                await backend.close()
            except Exception:
                pass
