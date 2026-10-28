"""网页工具：互联网搜索、阅读、查找及来源观察。"""
from __future__ import annotations

import asyncio
from copy import deepcopy

from searchos.skills.pipeline.access.tools.execute import ACCESS_TIMEOUT_S

TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "search",
     "description": "通过互联网搜索引擎检索公开网页，查找目标站点、API、库文档、教程、示例和排错资料。query 填写网页检索关键词，返回网页线索后用 open 阅读原文。本地代码和文件定位使用 exec 或当前角色的文件读取工具。",
     "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "互联网网页检索关键词，可组合站点、库名、版本、API 名或脱敏报错。"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "open",
     "description": "读取互联网网页正文。id_or_url 接收 HTTP(S) URL 或 search/open/find 返回的网页结果 ID；loc 按网页行号续读。",
     "parameters": {"type": "object", "properties": {"id_or_url": {"type": "string", "description": "互联网网页的 HTTP(S) URL 或网页结果 ID。"}, "loc": {"type": "integer", "default": 0, "description": "网页正文的起始行号。"}}, "required": ["id_or_url"]}}},
    {"type": "function", "function": {"name": "find",
     "description": "在当前已打开的互联网网页文本中按字面查找短语，定位文档段落、API 名称或错误说明；先用 open 打开目标网页。返回的网页结果 ID 可用 open 阅读。本地代码和文件定位使用 exec 或当前角色的文件读取工具。",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string", "description": "要在当前互联网网页文本中查找的字面短语。"}}, "required": ["pattern"]}}},
]


class ResearchBrowser:
    def __init__(self):
        from searchos.tools.simple_browser.state import BrowserState
        self.state = BrowserState()
        self.provider = None

    def _observation_metadata(self, content: str, cached_pages: set[int]) -> dict:
        """Read provenance from the source page, not its truncated display window."""
        metadata = {"source_url": "", "view_url": "", "fetch_status": "tool_error",
                    "content_source": "none", "live_evidence": False, "read_from_cache": False}
        # Simple Browser returns errors as text and leaves its last page open.
        # Do not attach that old page's identity or successful fetch status.
        if content.startswith("Error:") or not self.state.has_pages:
            metadata["error"] = content
            return metadata

        page = self.state.get_page()
        source_url = page.source_url or page.url
        source = self.state.get_page_by_url(source_url)
        metadata.update(source_url=source_url, view_url=page.url)
        if source is None:
            metadata["error"] = "research source page is unavailable"
            return metadata
        metadata["read_from_cache"] = id(source) in cached_pages
        for key in ("access_method", "proxy_mode", "reader_failure"):
            if key in source.metadata:
                metadata[key] = source.metadata[key]
        text = source.text or ""
        if source.url.startswith("search://"):
            metadata.update(fetch_status="not_attempted", content_source="search_results")
        elif text.startswith("[FETCH_ERROR]"):
            metadata.update(fetch_status="failed", error=text.split("\n\n", 1)[0][:1000])
        elif text.startswith(
            f"URL: {source.url}\n\n[NOTE] Live fetch failed; the content below is the "
            "search-engine snippet, not the full page.\n\n"
        ):
            # This prefix is produced by Simple Browser's snippet fallback.
            # A later open/find viewport may no longer display the warning.
            metadata.update(fetch_status="failed", content_source="search_fallback",
                            error="live page fetch failed; search-engine content is a research lead only")
        elif not text.strip():
            metadata.update(fetch_status="empty", content_source="page", error="research page is empty")
        else:
            from searchos.tools.simple_browser.backend.base import BrowserService
            from searchos.tools.simple_browser.backend.search_engine import SearchEngineBackend

            service = BrowserService._instance
            if (metadata.get("access_method") != "http_fallback" and service is not None
                    and isinstance(service.backend, SearchEngineBackend)):
                metadata.update(fetch_status="not_attempted", content_source="search_cache")
                return metadata
            # A previously fetched page remains page evidence; read_from_cache
            # makes clear that this call did not necessarily fetch it anew.
            metadata.update(fetch_status="ok", content_source="page", live_evidence=True)
        return metadata

    async def _http_fallback(self, metadata: dict, loc: int) -> tuple[str | None, str]:
        """Read public HTML/JSON once without bypassing proxy or TLS settings."""
        from searchos.tools.simple_browser.backend.aiohttp import AiohttpBackend
        from searchos.tools.simple_browser.image_reading import validate_public_url
        from searchos.tools.simple_browser.render import PageContents
        from searchos.tools.simple_browser.state import is_url_allowed

        url = metadata["source_url"]
        try:
            if not is_url_allowed(url):
                raise ValueError("source domain is excluded for this run")
            await asyncio.wait_for(validate_public_url(url), timeout=5)
            backend = AiohttpBackend(max_retries=0, trust_env=True, allow_redirects=False, allow_json=True)
            fetched = await asyncio.wait_for(backend.fetch(url, timeout=15), timeout=16)
            if not fetched.ok or not fetched.markdown.strip():
                return None, fetched.error or f"HTTP fallback returned status {fetched.status} or empty content"
            page = PageContents(url=fetched.url, title=fetched.title, text=fetched.markdown,
                urls=dict(fetched.links), metadata={"access_method": "http_fallback", "proxy_mode": "inherit",
                    "reader_failure": {key: metadata[key] for key in ("fetch_status", "content_source", "error")
                                       if key in metadata}})
            self.state.add_page(page)
            return self.state.show_page(loc=loc, view_tokens=2000), ""
        except Exception as exc:
            return None, str(exc) or type(exc).__name__

    async def dispatch(self, name: str, args: dict) -> dict:
        name = {'search': 'web_search', 'open': 'web_open', 'find': 'web_find'}.get(name, name)
        from searchos.tools.search_state import _workspace_var
        from searchos.tools.simple_browser import state, tools

        # Keep parent browser history and workspace pages untouched, including on error.
        browser_token = state._browser_var.set(self.state)
        workspace_token = _workspace_var.set(None)
        try:
            cached_pages = {id(page) for page in self.state.pages.values()}
            if name == "web_search":
                from searchos.tools.simple_browser.search import build_search_provider
                if self.provider is None:
                    self.provider = build_search_provider()
                query = str(args["query"]).strip()
                if not query:
                    raise ValueError("query must not be empty")
                results = state.apply_source_controls(await asyncio.wait_for(self.provider.search(query, 8), timeout=ACCESS_TIMEOUT_S))
                for result in results:
                    self.state.search_content_cache[result.url] = result
                self.state.search_history.append(query)
                self.state.add_page(state._build_search_page(query, results))
                content = self.state.show_page(loc=0, view_tokens=2000)
            else:
                tool = {"web_open": tools.open, "web_find": tools.find}[name]
                if name == "web_open":
                    target = str(args["id_or_url"])
                    if not target.isdigit() and not target.startswith(("https://", "http://")):
                        raise ValueError("research can open only result IDs or HTTP(S) URLs")
                    args = {"id_or_url": target, "loc": int(args.get("loc", 0)), "view_tokens": 2000}
                result = await asyncio.wait_for(tool.ainvoke({"name": tool.name, "args": args,
                    "id": "builder-research", "type": "tool_call"}), timeout=ACCESS_TIMEOUT_S)
                content = result.content
            metadata = self._observation_metadata(content, cached_pages)
            if name == "web_open" and metadata["fetch_status"] == "failed":
                recovered, fallback_error = await self._http_fallback(metadata, args.get("loc", 0))
                if recovered is not None:
                    content = recovered
                    metadata = self._observation_metadata(content, cached_pages)
                else:
                    metadata["fallback_error"] = fallback_error
            return {"content": content, "purpose": "research_only", "trusted_instructions": False, **metadata}
        finally:
            _workspace_var.reset(workspace_token)
            state._browser_var.reset(browser_token)


RESEARCH_TOOLS = deepcopy(TOOL_DEFINITIONS)


for tool in RESEARCH_TOOLS:
    function = tool['function']
    function['name'] = function['name'].removeprefix('web_')
    if function['name'] == 'open':
        function['description'] += ' Planner 另支持读取回执中明确给出的保存产物路径，用 offset 和 limit 分页；本地探测代码定位使用 exec。'
        function['parameters']['properties']['id_or_url']['description'] = (
            '互联网网页的 HTTP(S) URL、网页结果 ID，或回执中明确给出的保存产物路径。')
        function['parameters']['properties'].update(
            offset={'type': 'integer', 'default': 0},
            limit={'type': 'integer', 'default': 16000, 'minimum': 1, 'maximum': 24000})
