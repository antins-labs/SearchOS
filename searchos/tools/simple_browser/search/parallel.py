"""Anonymous web search through Parallel's Streamable HTTP MCP endpoint."""

from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError, version
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation, PaginatedRequestParams
from pydantic import BaseModel, ValidationError

from searchos.tools.simple_browser.search.base import SearchProvider, SearchResult

_SEARCH_TIMEOUT = 20.0
_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_SNIPPET_CHARS = 1600


class _BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream) -> None:
        self._stream = stream

    async def __aiter__(self):
        size = 0
        async for chunk in self._stream:
            size += len(chunk)
            if size > _MAX_RESPONSE_BYTES:
                raise httpx.ReadError("Parallel MCP response exceeds 1 MiB")
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


async def _omit_cookies(request: httpx.Request) -> None:
    # This client uses MCP session headers without replaying server-issued cookies.
    request.headers.pop("Cookie", None)


async def _bound_response(response: httpx.Response) -> None:
    # Count uncompressed bytes before the SDK buffers JSON or an SSE event.
    if response.headers.get("content-encoding", "identity").lower() != "identity":
        raise httpx.ReadError("Unexpected compression on a Parallel MCP response")
    response.stream = _BoundedStream(response.stream)


class _Hit(BaseModel):
    url: str
    title: str | None = None
    excerpts: list[str]


class _SearchPayload(BaseModel):
    results: list[_Hit]


class ParallelProvider(SearchProvider):
    """Map Parallel web_search hits to Simple Browser's search results."""

    ENDPOINT = "https://mcp.parallel.ai/mcp"

    @property
    def name(self) -> str:
        return "parallel"

    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        if max_results <= 0:
            return []
        query = query.strip()
        if not query:
            raise ValueError("Parallel search requires a nonempty query")

        try:
            release = version("searchos")
        except PackageNotFoundError:
            release = ""
        user_agent = f"SearchOS/{release}" if release else "SearchOS"
        client_info = Implementation(name="SearchOS", version=release) if release else None
        try:
            async with (
                asyncio.timeout(_SEARCH_TIMEOUT),
                httpx.AsyncClient(
                    headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
                    timeout=httpx.Timeout(5.0, read=_SEARCH_TIMEOUT),
                    follow_redirects=False,
                    max_redirects=0,  # The MCP transport follows same-origin redirects itself.
                    event_hooks={"request": [_omit_cookies], "response": [_bound_response]},
                ) as http,
                streamable_http_client(self.ENDPOINT, http_client=http) as (rx, tx, _),
                ClientSession(rx, tx, client_info=client_info) as session,
            ):
                await session.initialize()
                page = await session.list_tools()
                while not any(tool.name == "web_search" for tool in page.tools):
                    if not page.nextCursor:
                        raise RuntimeError("Parallel MCP does not advertise web_search")
                    page = await session.list_tools(
                        params=PaginatedRequestParams(cursor=page.nextCursor)
                    )
                result = await session.call_tool(
                    "web_search", {"objective": query, "search_queries": [query]}
                )
        except TimeoutError as exc:
            raise RuntimeError("Parallel search timed out") from exc
        except ExceptionGroup as exc:
            raise RuntimeError("Parallel MCP search request failed") from exc

        if result.isError:
            raise RuntimeError("Parallel web_search returned a tool error")
        try:
            hits = _SearchPayload.model_validate(result.structuredContent).results
        except ValidationError as exc:
            raise RuntimeError("Parallel web_search returned invalid results") from exc

        results = []
        for hit in hits:
            try:
                parsed = urlsplit(hit.url)
            except ValueError:
                continue
            if (
                parsed.scheme not in ("https", "http")
                or not parsed.hostname
                or parsed.username is not None
                or any(char.isspace() for char in hit.url)
            ):
                continue
            snippet = " ".join(" ".join(hit.excerpts).split())
            if len(snippet) > _MAX_SNIPPET_CHARS:
                snippet = snippet[:_MAX_SNIPPET_CHARS] + "…"
            results.append(SearchResult(
                url=hit.url,
                title=" ".join((hit.title or "").split())[:240],
                snippet=snippet,
            ))
            if len(results) == max_results:
                break
        return results
