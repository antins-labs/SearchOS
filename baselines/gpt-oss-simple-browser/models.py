"""Data models for the search agent, inspired by GPT-OSS simple_browser."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PageContents:
    """Structured representation of a web page, matching GPT-OSS PageContents design."""

    url: str
    title: str
    text: str
    urls: dict[str, str] = field(default_factory=dict)  # link_id → url mapping
    snippets: dict[str, Extract] | None = None  # Search result snippets

    @property
    def is_search_results(self) -> bool:
        return self.snippets is not None


@dataclass
class Extract:
    """A search result snippet or quotable extract."""

    url: str
    text: str
    title: str
    line_idx: int | None = None


@dataclass
class SearchResult:
    """A single search result from the RAG API."""

    title: str
    url: str
    snippet: str
    content: str = ""
    score: float = 1.0
