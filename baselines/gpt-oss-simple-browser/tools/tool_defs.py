"""
Tool definitions for the search agent.
Provides JSON schemas in both OpenAI and Claude formats.
"""

from __future__ import annotations


# ---- OpenAI function calling format ----

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for information. Returns a list of search results with titles, "
                "URLs, and snippets. Use this to find relevant web pages for the user's question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_page",
            "description": (
                "Open a link from the CURRENTLY displayed page, or scroll it.\n"
                "- id (numeric): open a link by its [id] shown on the current page. "
                "These IDs are page-specific — they change every time a new page is displayed. "
                "After opening a page, the previous page's IDs are no longer valid. "
                "To open another search result, use its URL directly or do a new web_search.\n"
                "- id (URL string): open a URL directly, regardless of the current page.\n"
                "- loc only (no id): scroll the current page to the given line number.\n"
                "The page content is displayed with line numbers (L0, L1, ...)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {
                        "description": (
                            "A link ID from the current page (e.g. 0, 1, 2 — must exist in the currently displayed page), "
                            "or a full URL string (e.g. \"https://...\") to open directly."
                        ),
                    },
                    "loc": {
                        "type": "integer",
                        "description": "Line number to scroll to (0-indexed). Use this to view different parts of a page.",
                        "default": 0,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_in_page",
            "description": (
                "Search for a text pattern within the current page. "
                "Returns matching lines with their line numbers. "
                "The pattern is case-insensitive."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The text pattern to search for in the current page.",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
]


# ---- Claude tool_use format ----

CLAUDE_TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web for information. Returns a list of search results with titles, "
            "URLs, and snippets. Use this to find relevant web pages for the user's question."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "open_page",
        "description": (
            "Open a link from the CURRENTLY displayed page, or scroll it.\n"
            "- id (numeric): open a link by its [id] shown on the current page. "
            "These IDs are page-specific — they change every time a new page is displayed. "
            "After opening a page, the previous page's IDs are no longer valid. "
            "To open another search result, use its URL directly or do a new web_search.\n"
            "- id (URL string): open a URL directly, regardless of the current page.\n"
            "- loc only (no id): scroll the current page to the given line number.\n"
            "The page content is displayed with line numbers (L0, L1, ...)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {
                    "description": (
                        "A link ID from the current page (e.g. 0, 1, 2 — must exist in the currently displayed page), "
                        "or a full URL string (e.g. \"https://...\") to open directly."
                    ),
                },
                "loc": {
                    "type": "integer",
                    "description": "Line number to scroll to (0-indexed). Use this to view different parts of a page.",
                    "default": 0,
                },
            },
        },
    },
    {
        "name": "find_in_page",
        "description": (
            "Search for a text pattern within the current page. "
            "Returns matching lines with their line numbers. "
            "The pattern is case-insensitive."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The text pattern to search for in the current page.",
                },
            },
            "required": ["pattern"],
        },
    },
]


def get_tool_definitions() -> list[dict]:
    """Get tool definitions in OpenAI function calling format."""
    return OPENAI_TOOLS


def get_tool_definitions_claude() -> list[dict]:
    """Get tool definitions in Claude tool_use format."""
    return CLAUDE_TOOLS
