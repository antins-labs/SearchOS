"""生成器专用的 Simple Browser 会话；研究材料不进入任务证据或技能包。"""
from __future__ import annotations

import asyncio


TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "web_search",
     "description": "Research site documentation and access methods using the configured web search provider. Results are external research, not proof that a generated CLI works.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "web_open",
     "description": "Read a research result ID or HTTP(S) URL with Simple Browser; use loc to read later lines. This is a document reader, not a logged-in interactive browser.",
     "parameters": {"type": "object", "properties": {"id_or_url": {"type": "string"}, "loc": {"type": "integer", "default": 0}}, "required": ["id_or_url"]}}},
    {"type": "function", "function": {"name": "web_find",
     "description": "Find a short literal phrase in the current research page; returned IDs can be opened.",
     "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}}},
]


class ResearchBrowser:
    def __init__(self):
        from searchos.tools.simple_browser.state import BrowserState
        self.state = BrowserState()
        self.provider = None

    async def dispatch(self, name: str, args: dict) -> dict:
        from searchos.tools.simple_browser import state, tools
        from searchos.tools.search_state import _workspace_var

        # Keep parent browser history and workspace pages untouched, including on error.
        browser_token = state._browser_var.set(self.state)
        workspace_token = _workspace_var.set(None)
        try:
            if name == "web_search":
                from searchos.tools.simple_browser.search import build_search_provider
                if self.provider is None:
                    self.provider = build_search_provider()
                query = str(args["query"]).strip()
                if not query:
                    raise ValueError("query must not be empty")
                results = state.apply_source_controls(await asyncio.wait_for(self.provider.search(query, 8), timeout=40))
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
                    "id": "builder-research", "type": "tool_call"}), timeout=45)
                content = result.content
            return {"content": content, "purpose": "research_only", "trusted_instructions": False}
        finally:
            _workspace_var.reset(workspace_token)
            state._browser_var.reset(browser_token)
