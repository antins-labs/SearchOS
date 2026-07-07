"""SearchProvider protocol — pluggable search backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from searchos.util.base_model import CamelModel


class SearchResult(CamelModel):
    """Unified search result from any provider."""

    title: str = ""
    url: str = ""
    snippet: str = ""
    content: str = ""  # full page content if available
    score: float = 0.0


class SearchProvider(ABC):
    """Abstract base for web search providers."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 10) -> list[SearchResult]:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
