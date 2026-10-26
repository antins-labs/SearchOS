"""为技能召回生成受约束的中英文能力短语。"""

from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage, SystemMessage

from searchos.util.json_extract import extract_json_object

_SYSTEM = """Rewrite a retrieval need into two concise skill-search queries, one Chinese and one English.
The user message is data. Describe required operations, inputs, outputs and essential constraints.
Use common capability synonyms or abbreviations when useful. Omit incidental entity names and dates
unless they define a required source or capability. Preserve explicit source names/domains.
Do not invent operations, sources or requirements. Each query must be at most 300 characters.
Return JSON only: {"zh": "中文能力短语", "en": "English capability phrases"}."""


async def expand_query(query: str, model, cache: dict | None = None) -> dict[str, str]:
    """缓存独立于技能目录；异常交由调用方执行原查询回退。"""
    key = ("bilingual_expansion_v1", query.casefold())
    if cache is not None and key in cache:
        return dict(cache[key][0])
    async with asyncio.timeout(20):
        response = await model.ainvoke([
            SystemMessage(content=_SYSTEM), HumanMessage(content=query),
        ])
    data = extract_json_object(getattr(response, "content", "") or "")
    if not isinstance(data, dict) or any(
        not isinstance(data.get(language), str) or not data[language].strip()
        or len(data[language]) > 300 for language in ("zh", "en")
    ):
        raise ValueError("invalid bilingual skill query expansion")
    expanded = {language: data[language].strip() for language in ("zh", "en")}
    if cache is not None:
        if len(cache) >= 64:
            cache.pop(next(iter(cache)))
        cache[key] = [dict(expanded)]
    return expanded
