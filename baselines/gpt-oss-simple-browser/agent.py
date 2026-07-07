"""
Search Agent - ReAct-style agent loop for search and browse.
Core loop: think → act (tool call) → observe → ... → finish.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from .config import AgentConfig
from .llm.base import BaseLLM, LLMResponse, TokenUsage, ToolCall
from .models import PageContents, SearchResult
from .state import BrowserState, find_in_page
from .tools.browser import fetch_page
from .tools.search import build_search_page, web_search
from .tools.tool_defs import get_tool_definitions, get_tool_definitions_claude

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are a search assistant. Your task is to answer the user's question by searching the web and browsing pages.
"""


class SearchAgent:
    """ReAct-style search agent that uses tools to find and browse information."""

    def __init__(self, llm: BaseLLM, config: AgentConfig):
        self.llm = llm
        self.config = config
        self.state = BrowserState()
        self._is_claude = config.llm_provider == "claude"
        # Cache: url → SearchResult content from search API
        self._search_content_cache: dict[str, SearchResult] = {}
        # Saved after run() completes
        self.last_query: str = ""
        self.last_answer: str = ""
        self.last_messages: list[dict] = []
        self.last_tools: list[dict] = []
        self.total_usage = TokenUsage()
        self.tool_rounds: int = 0

    async def run(self, query: str) -> str:
        """Execute the agent loop for a given query.

        Returns the final answer string.
        """
        self.last_query = query
        messages = self._build_initial_messages(query)
        tools = get_tool_definitions_claude() if self._is_claude else get_tool_definitions()

        for iteration in range(self.config.max_iterations):
            if self.config.verbose:
                print(f"\n--- Iteration {iteration + 1}/{self.config.max_iterations} ---")

            response = await self.llm.chat_with_tools(
                messages=messages,
                tools=tools,
                system_prompt=SYSTEM_PROMPT,
            )
            self.total_usage += response.usage

            # Log thinking/reasoning
            if self.config.verbose and response.thinking:
                print(f"[Thinking] {response.thinking}")
            if self.config.verbose and response.content:
                print(f"[Content] {response.content}")

            # Process tool calls
            if response.has_tool_calls:
                self.tool_rounds += 1
                messages.append(self._build_assistant_message(response))

                for tool_call in response.tool_calls:
                    if self.config.verbose:
                        print(f"[Tool Call] {tool_call.name}({json.dumps(tool_call.arguments, ensure_ascii=False)})")

                    # Execute tool and get result
                    result = await self._execute_tool(tool_call)

                    if self.config.verbose:
                        # Show truncated result
                        preview = result[:500] + "..." if len(result) > 500 else result
                        print(f"[Tool Result] {preview}")

                    messages.append(self._build_tool_result_message(tool_call, result))
            else:
                if response.content:
                    self._save_state(messages, response.content, tools)
                    return response.content
                messages.append(self._build_assistant_message(response))

        fallback = "Reached maximum iterations without finding an answer."
        self._save_state(messages, fallback, tools)
        return fallback

    def _save_state(self, messages: list[dict], answer: str, tools: list[dict]) -> None:
        """Store messages, tools and answer for later retrieval."""
        self.last_messages = messages
        self.last_answer = answer
        self.last_tools = tools

    def save_result(self, output_dir: str) -> str:
        """Save the last run's query, answer, and messages to a JSON file.

        Args:
            output_dir: Directory to save the result file.

        Returns:
            The path to the saved file.
        """
        os.makedirs(output_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"result_{ts}.json"
        filepath = os.path.join(output_dir, filename)

        data = {
            "query": self.last_query,
            "answer": self.last_answer,
            "system_prompt": SYSTEM_PROMPT,
            "tools": self.last_tools,
            "messages": self.last_messages,
            "metadata": {
                "model": self.config.model_name,
                "provider": self.config.llm_provider,
                "max_iterations": self.config.max_iterations,
                "tool_rounds": self.tool_rounds,
                "usage": self.total_usage.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return filepath

    async def _execute_tool(self, tool_call: ToolCall) -> str:
        """Execute a tool call and return the result as a string."""
        name = tool_call.name
        args = tool_call.arguments

        try:
            if name == "web_search":
                return await self._do_search(args.get("query", ""))
            elif name == "open_page":
                return await self._do_open(args)
            elif name == "find_in_page":
                return await self._do_find(args.get("pattern", ""))
            else:
                return f"Unknown tool: {name}"
        except Exception as e:
            logger.error("Tool execution error: %s", e)
            return f"Error: {e}"

    async def _do_search(self, query: str) -> str:
        """Execute web_search and return formatted results."""
        results = await web_search(query, page_size=self.config.search_page_size)
        for r in results:
            if r.url and r.content:
                self._search_content_cache[r.url] = r
        page = build_search_page(query, results)
        self.state.add_page(page)
        return self.state.show_page(
            loc=0,
            view_tokens=self.config.view_tokens,
            wrap_width=self.config.line_wrap_width,
        )

    async def _do_open(self, args: dict) -> str:
        """Execute open_page: open a link, URL, or scroll current page."""
        page_id = args.get("id")
        loc = args.get("loc", 0)

        if page_id is not None:
            if isinstance(page_id, str) and (page_id.startswith("http://") or page_id.startswith("https://")):
                # Direct URL open
                url = page_id
            elif isinstance(page_id, (int, float)) or (isinstance(page_id, str) and page_id.isdigit()):
                # Link ID from current page
                link_id = str(int(page_id))
                if not self.state.has_pages:
                    return "Error: No page is currently open. Use web_search first."
                current_page = self.state.get_page()
                if link_id not in current_page.urls:
                    return f"Error: Link ID {link_id} not found on current page. Available IDs: {list(current_page.urls.keys())[:20]}"
                
                url = current_page.urls[link_id]

                # If opening from search results, get the snippet's line_idx
                if current_page.snippets and link_id in current_page.snippets:
                    snippet = current_page.snippets[link_id]
                    if snippet.line_idx is not None and loc == 0:
                        loc = max(0, snippet.line_idx - 4)
            else:
                return f"Error: Invalid id parameter: {page_id}"

            cached = self.state.get_page_by_url(url)
            if cached:
                self.state.add_page(cached)
            elif url in self._search_content_cache:
                page = self._build_page_from_cache(url)
                self.state.add_page(page)
            else:
                page = await fetch_page(url)
                self.state.add_page(page)
        else:
            if not self.state.has_pages:
                return "Error: No page is currently open. Use web_search first."

        return self.state.show_page(
            loc=loc,
            view_tokens=self.config.view_tokens,
            wrap_width=self.config.line_wrap_width,
        )

    def _find_last_search_page(self) -> PageContents | None:
        """Find the most recent search results page in the page stack."""
        for url in reversed(self.state.page_stack):
            page = self.state.pages[url]
            if page.is_search_results:
                return page
        return None

    def _build_page_from_cache(self, url: str) -> PageContents:
        """Build a PageContents from cached search API content."""
        cached = self._search_content_cache[url]
        return PageContents(
            url=url,
            title=cached.title,
            text=f"\nURL: {url}\n\n{cached.content}",
            urls={},
        )

    async def _do_find(self, pattern: str) -> str:
        """Execute find_in_page on the current page."""
        if not self.state.has_pages:
            return "Error: No page is currently open. Use web_search first."

        current_page = self.state.get_page()
        if current_page.snippets is not None:
            return "Error: Cannot use find on a search results page. Open a page first."

        result_page = find_in_page(
            pattern=pattern.lower(),
            page=current_page,
            wrap_width=self.config.line_wrap_width,
        )
        self.state.add_page(result_page)
        return self.state.show_page(
            loc=0,
            view_tokens=self.config.view_tokens,
            wrap_width=self.config.line_wrap_width,
        )

    # ---- Message builders ----

    def _build_initial_messages(self, query: str) -> list[dict]:
        """Build initial message list with the user's query."""
        return [{"role": "user", "content": query}]

    def _build_assistant_message(self, response: LLMResponse) -> dict:
        """Build an assistant message from the LLM response."""
        if self._is_claude:
            content = []
            if response.thinking:
                content.append({"type": "thinking", "thinking": response.thinking})
            if response.content:
                content.append({"type": "text", "text": response.content})
            for tc in response.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            return {"role": "assistant", "content": content}
        else:
            msg: dict[str, Any] = {"role": "assistant"}
            if response.thinking:
                msg["reasoning_content"] = response.thinking
            if response.content:
                msg["content"] = response.content
            else:
                msg["content"] = None
            if response.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]
            return msg

    def _build_tool_result_message(self, tool_call: ToolCall, result: str) -> dict:
        """Build a tool result message."""
        if self._is_claude:
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": result,
                    }
                ],
            }
        else:
            return {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            }
