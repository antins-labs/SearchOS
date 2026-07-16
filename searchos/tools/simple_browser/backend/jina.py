"""Jina Reader backend: GETs ``https://r.jina.ai/{url}`` → LLM-ready markdown."""

from __future__ import annotations

import asyncio
import os
import re

import aiohttp

from searchos.tools.simple_browser.backend.base import FetchResult
from searchos.tools.simple_browser.usage import record_jina_call

_JINA_BASE = "https://r.jina.ai/"


def _parse_jina_markdown(text: str) -> tuple[str, dict[str, str]]:
    """Pull title and links from Jina's response (markdown with an optional
    ``Links/Buttons:`` section appended when X-With-Links-Summary is set)."""
    title = ""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# "):
            title = s[2:].strip()
            break
        if s.startswith("Title:"):
            title = s[len("Title:"):].strip()
            break

    links: dict[str, str] = {}
    idx = text.find("Links/Buttons:")
    if idx == -1:
        idx = text.find("Links:")
    if idx != -1:
        for i, m in enumerate(re.finditer(r"\[[^\]]*\]\((https?://[^)\s]+)\)", text[idx:])):
            if i >= 80:
                break
            links[f"L{i}"] = m.group(1)
    return title, links


class JinaReaderBackend:
    """GETs ``https://r.jina.ai/{url}`` and gets back LLM-ready markdown.
    No local HTML pipeline / Playwright. Note: ``html`` field is empty, so
    CSS-selector access skills won't work on this backend."""

    def __init__(self, *, api_key: str = "", proxy: str | None = None) -> None:
        self._api_key = api_key or os.getenv("JINA_API_KEY", "")
        self._proxy = (
            proxy
            or os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
            or os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        )
        # Independent call counter (markdown + html paths). Exposed via
        # ``api_calls`` and consumed by eval/runner for per-task delta.
        self.api_calls = 0

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"X-Retain-Images": "alt"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    async def fetch(
        self, url: str, *, query: str = "", timeout: float = 60.0,
    ) -> FetchResult:
        target = _JINA_BASE + url
        self.api_calls += 1
        record_jina_call()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    target,
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    proxy=self._proxy,
                ) as resp:
                    text = await resp.text(errors="replace")
                    if resp.status != 200:
                        return FetchResult(
                            url=url, title="Error",
                            markdown=f"HTTP {resp.status}: {text[:200]}",
                            status=resp.status, error=f"HTTP {resp.status}",
                        )
                    title, links = _parse_jina_markdown(text)
                    return FetchResult(
                        url=url, title=title, markdown=text,
                        links=links, status=200,
                    )
        except Exception as e:  # noqa: BLE001
            return FetchResult(
                url=url, title="Error",
                markdown=f"Fetch failed: {e}",
                status=0, error=str(e),
            )

    async def fetch_html(self, url: str, *, timeout: float = 60.0) -> str:
        """Jina Reader with ``X-Return-Format: html``. ``""`` on failure."""
        target = _JINA_BASE + url
        self.api_calls += 1
        record_jina_call()
        headers = {**self._headers(), "X-Return-Format": "html"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    target,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    proxy=self._proxy,
                ) as resp:
                    if resp.status != 200:
                        return ""
                    return await resp.text(errors="replace")
        except Exception:  # noqa: BLE001
            return ""

    async def fetch_many(
        self, urls: list[str], *, query: str = "", timeout: float = 60.0,
    ) -> list[FetchResult]:
        coros = [self.fetch(u, query=query, timeout=timeout) for u in urls]
        return await asyncio.gather(*coros, return_exceptions=False)

    async def close(self) -> None:
        return None
