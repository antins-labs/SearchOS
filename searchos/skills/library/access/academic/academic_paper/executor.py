"""Academic Paper Search — executable access skill.

Searches Semantic Scholar, DBLP, and arXiv in parallel.
Returns structured paper metadata (title, authors, abstract, citations, URL).
No API key required. Does not use browser tools.
"""

from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from searchos.skills.core.contract import SkillContext

logger = logging.getLogger(__name__)

_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"
_TIMEOUT = 30.0


async def execute(params: dict[str, Any], ctx: SkillContext) -> dict[str, Any]:
    """Search academic databases for papers.

    Args:
        params:
            query: Search query string (required)
            num_results: Max papers per source (default 5, max 10)
            year_range: e.g. "2023-2025" or "2024-" (optional)
            source: "all" | "semantic_scholar" | "dblp" | "arxiv" (default "all")
        ctx: SkillContext. Unused — this skill uses direct HTTP calls.
    """
    query = params.get("query", "")
    if not query:
        return {"error": "query is required"}

    num_results = min(params.get("num_results", 5), 10)
    year_range = params.get("year_range", "")
    source = params.get("source", "all")

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        papers: list[dict] = []

        if source == "all":
            results = await asyncio.gather(
                _search_semantic_scholar(client, query, num_results, year_range),
                _search_dblp(client, query, num_results, year_range),
                _search_arxiv(client, query, num_results, year_range),
                return_exceptions=True,
            )
            for label, result in zip(["Semantic Scholar", "DBLP", "arXiv"], results):
                if isinstance(result, Exception):
                    logger.warning("academic_paper: %s failed: %s", label, result)
                else:
                    papers.extend(result)
            papers = _deduplicate(papers)
        elif source == "semantic_scholar":
            papers = await _search_semantic_scholar(client, query, num_results, year_range)
        elif source == "dblp":
            papers = await _search_dblp(client, query, num_results, year_range)
        elif source == "arxiv":
            papers = await _search_arxiv(client, query, num_results, year_range)
        else:
            return {"error": f"unknown source: {source}"}

    if not papers:
        return {"papers": [], "status": "empty"}

    return {"papers": papers, "status": "ok"}


# ── Semantic Scholar ─────────────────────────────────────────────

async def _search_semantic_scholar(
    client: httpx.AsyncClient, query: str, num_results: int, year_range: str,
) -> list[dict]:
    params: dict[str, Any] = {
        "query": query,
        "limit": num_results,
        "fields": "title,authors,abstract,year,citationCount,url,venue,journal,paperId",
    }
    if year_range:
        params["year"] = year_range

    resp = await client.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params=params,
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    data = resp.json()

    papers = data.get("data", [])
    for p in papers:
        p["_source"] = "Semantic Scholar"
        if not p.get("venue"):
            journal = p.get("journal")
            if isinstance(journal, dict):
                p["venue"] = journal.get("name", "")
    return papers


# ── DBLP ─────────────────────────────────────────────────────────

async def _search_dblp(
    client: httpx.AsyncClient, query: str, num_results: int, year_range: str,
) -> list[dict]:
    resp = await client.get(
        "https://dblp.org/search/publ/api",
        params={"q": query, "format": "json", "h": num_results, "c": 0},
        headers={"Accept": "application/json"},
    )
    resp.raise_for_status()
    hits = resp.json().get("result", {}).get("hits", {}).get("hit", [])
    if not hits:
        return []

    year_start, year_end = _parse_year_range(year_range)
    papers = []
    for hit in hits:
        info = hit.get("info", {})
        year_str = info.get("year", "")
        year = int(year_str) if year_str.isdigit() else None

        if year is not None:
            if year_start and year < year_start:
                continue
            if year_end and year > year_end:
                continue

        raw_authors = info.get("authors", {}).get("author", [])
        if isinstance(raw_authors, dict):
            raw_authors = [raw_authors]
        authors = [{"name": a.get("text", a) if isinstance(a, dict) else str(a)} for a in raw_authors]

        url = info.get("ee", "") or info.get("url", "")
        if isinstance(url, list):
            url = url[0] if url else ""

        papers.append({
            "title": info.get("title", "Untitled"),
            "authors": authors,
            "abstract": "",
            "year": year or "N/A",
            "citationCount": None,
            "url": url,
            "venue": info.get("venue", ""),
            "paperId": info.get("key", ""),
            "_source": "DBLP",
        })
    return papers


# ── arXiv ────────────────────────────────────────────────────────

async def _search_arxiv(
    client: httpx.AsyncClient, query: str, num_results: int, year_range: str,
) -> list[dict]:
    search_query = f"all:{query}"
    if year_range:
        ys, ye = _parse_year_range(year_range)
        if ys or ye:
            start_date = f"{ys or 1991}01010000"
            end_date = f"{ye or 2099}12312359"
            search_query += f" AND submittedDate:[{start_date} TO {end_date}]"

    resp = await client.get(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": search_query,
            "start": 0,
            "max_results": num_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        },
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    papers = []
    for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
        title = re.sub(r"\s+", " ", entry.findtext(f"{{{_ATOM_NS}}}title", "Untitled")).strip()
        authors = [
            {"name": a.findtext(f"{{{_ATOM_NS}}}name", "")}
            for a in entry.findall(f"{{{_ATOM_NS}}}author")
            if a.findtext(f"{{{_ATOM_NS}}}name", "")
        ]
        abstract = re.sub(r"\s+", " ", entry.findtext(f"{{{_ATOM_NS}}}summary", "")).strip()
        url = entry.findtext(f"{{{_ATOM_NS}}}id", "") or ""
        published = entry.findtext(f"{{{_ATOM_NS}}}published", "")
        year: int | str = "N/A"
        if published and len(published) >= 4:
            try:
                year = int(published[:4])
            except ValueError:
                pass
        primary_cat = entry.find(f"{{{_ARXIV_NS}}}primary_category")
        venue = f"arXiv:{primary_cat.get('term', '')}" if primary_cat is not None else "arXiv"
        paper_id = url.split("/abs/")[-1] if "/abs/" in url else ""

        papers.append({
            "title": title, "authors": authors, "abstract": abstract,
            "year": year, "citationCount": None, "url": url,
            "venue": venue, "paperId": paper_id, "_source": "arXiv",
        })
    return papers


# ── Helpers ──────────────────────────────────────────────────────

def _parse_year_range(year_range: str) -> tuple[int | None, int | None]:
    if not year_range:
        return None, None
    parts = year_range.split("-")
    start = int(parts[0]) if parts[0].strip().isdigit() else None
    end = int(parts[1]) if len(parts) > 1 and parts[1].strip().isdigit() else None
    return start, end


def _deduplicate(papers: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for paper in papers:
        key = re.sub(r"\s+", " ", paper.get("title", "").lower().strip())
        if not key:
            continue
        if key in seen:
            existing = seen[key]
            if not existing.get("abstract") and paper.get("abstract"):
                seen[key] = paper
            elif (existing.get("abstract") and paper.get("abstract")
                  and existing.get("citationCount") is None
                  and paper.get("citationCount") is not None):
                seen[key] = paper
        else:
            seen[key] = paper
    return list(seen.values())
