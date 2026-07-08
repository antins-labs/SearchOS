"""RagFlow search provider — 内部 RAG+LLM 搜索接口（外部环境不可用）.

Endpoint 与 userId 凭证均从环境变量读取：RAGFLOW_ENDPOINT / RAGFLOW_USER_ID。
"""

from __future__ import annotations

import logging
import os
import re

import httpx

from searchos.tools.simple_browser.search.base import SearchProvider, SearchResult

logger = logging.getLogger(__name__)

REPEATED_PATTERN = re.compile(r"[-_—*/～~\s]{20,}")


def _clean(text: str) -> str:
    if not text or not isinstance(text, str):
        return text
    return re.sub(REPEATED_PATTERN, ". ", text)


class RagFlowProvider(SearchProvider):
    """公司内部 RAG 搜索 provider."""

    def __init__(
        self,
        domain: str = "google",  # aligned with baseline — Google index gives best quality
        user_id: str = "",
        source: str = "ins_smart_agent",
    ) -> None:
        self._domain = domain
        # 端点与凭证不入库：从 RAGFLOW_ENDPOINT / RAGFLOW_USER_ID 环境变量读取
        # （实例化时读，运行中改 env 后新构造的 provider 立即生效）
        self._endpoint = os.environ.get("RAGFLOW_ENDPOINT", "")
        self._user_id = user_id or os.environ.get("RAGFLOW_USER_ID", "")
        if not self._endpoint:
            logger.warning("RAGFLOW_ENDPOINT 未设置，RagFlow 搜索不可用")
        if not self._user_id:
            logger.warning("RAGFLOW_USER_ID 未设置，RagFlow 搜索请求可能被拒绝")
        self._source = source

    @property
    def name(self) -> str:
        return "ragflow"

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        payload = {
            "domain": self._domain,
            "extParams": {},
            "page": 0,
            "pageSize": max_results,
            "query": query,
            "searchMode": "RAG_LLM",
            "source": self._source,
            "userId": self._user_id,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self._endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for item in data.get("searchDocs", []):
            # 接口返回字段: title, url, docAbstract, doc, abstractExtract
            abstract = (
                item.get("docAbstract", "")
                or item.get("abstract", "")
                or item.get("abstractExtract", "")
            )
            content = item.get("doc", "") or abstract
            results.append(SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=_clean(abstract),
                content=_clean(content),
                score=item.get("relScore", 0.0) or 0.0,
            ))

        logger.info("RagFlow search '%s': %d results", query, len(results))
        return results
