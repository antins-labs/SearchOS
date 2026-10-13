"""openalex_work — 从 OpenAlex API 检索学术作品。

修复记录：
- 修正 URL 模板：使用 aiohttp 的 params 参数自动编码，避免手动拼接导致的占位符残留
- 修正参数映射：CLI --per-page 正确映射到 API per-page 参数
- 增加分页支持：支持 page 参数和 cursor 分页
- 增加过滤与排序：支持 filter、sort 参数
- 增加单作品检索：通过 openalex_id 直接获取作品详情
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlencode

import aiohttp

from typing import Any as SkillContext

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.openalex.org/works"
_HEADERS = {"Accept": "application/json"}
_RESULT_PATH = ["results"]
_FIELDS = {
    "title": ["display_name"],
    "url": ["id"],
    "publication_year": ["publication_year"],
    "doi": ["doi"],
    "type": ["type"],
}


def _walk(obj: Any, path: list[str]) -> Any:
    """Walk a nested dict/list by path keys."""
    for key in path:
        if isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return None
    return obj


def _extract_field(item: Any, path: list[str]) -> Any:
    """Extract a field from an item by path."""
    val = _walk(item, path) if path else item
    if isinstance(val, list):
        return [str(v) for v in val if v is not None]
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)[:500]
    return str(val)[:2000]


def _build_url(params: dict[str, Any]) -> str:
    """Build OpenAlex API URL with proper parameter encoding."""
    query_params = {}
    
    # Map CLI parameter names to OpenAlex API parameter names
    if "query" in params and params["query"]:
        query_params["search"] = params["query"]
    
    if "per_page" in params:
        query_params["per-page"] = int(params["per_page"])
    
    if "page" in params:
        query_params["page"] = int(params["page"])
    
    if "filter" in params and params["filter"]:
        query_params["filter"] = params["filter"]
    
    if "sort" in params and params["sort"]:
        query_params["sort"] = params["sort"]
    
    if "cursor" in params and params["cursor"]:
        query_params["cursor"] = params["cursor"]
    
    if "openalex_id" in params and params["openalex_id"]:
        # Direct work lookup by ID
        work_id = params["openalex_id"]
        # Handle full URL or just the ID
        if work_id.startswith("https://"):
            work_id = work_id.split("/")[-1]
        return f"{_BASE_URL}/{work_id}"
    
    # Build query string with proper encoding
    if query_params:
        return f"{_BASE_URL}?{urlencode(query_params, doseq=True)}"
    return _BASE_URL


async def execute(params: dict[str, Any], ctx: SkillContext) -> dict[str, Any]:
    """Execute OpenAlex API query and return structured results."""
    # Build URL with proper encoding
    url = _build_url(params)
    
    timeout = aiohttp.ClientTimeout(total=30.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, headers=_HEADERS) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    return {
                        "error": f"http_{resp.status}",
                        "url": url,
                        "message": text[:500] if text else None
                    }
                body = await resp.read()
        except aiohttp.ClientError as e:
            return {"error": f"fetch_{type(e).__name__}: {e}", "url": url}
        except Exception as e:
            return {"error": f"fetch_{type(e).__name__}: {e}", "url": url}
    
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return {"error": f"json_decode: {e}", "url": url}
    
    # Handle single work lookup
    if "openalex_id" in params and params["openalex_id"]:
        # Single work response is the work object itself
        work = data
        if not isinstance(work, dict) or "id" not in work:
            return {"error": "invalid_work_response", "url": url}
        
        result = {}
        for fname, fpath in _FIELDS.items():
            result[fname] = _extract_field(work, list(fpath) if isinstance(fpath, list) else [fpath])
        # Add additional useful fields
        result["cited_by_count"] = work.get("cited_by_count")
        result["openalex_id"] = work.get("id", "").split("/")[-1]
        
        return {
            "results": [result],  # Return as array for consistency
            "count": 1,
            "source": url
        }
    
    # Handle search results
    items = _walk(data, list(_RESULT_PATH)) if _RESULT_PATH else data
    if items is None:
        return {
            "error": "result_path_miss",
            "keys": list(data.keys()) if isinstance(data, dict) else None,
            "url": url
        }
    if not isinstance(items, list):
        items = [items]
    
    # Limit results if num_results specified
    num = int(params.get("num_results", 0) or 0)
    if num > 0:
        items = items[:num]
    
    results = []
    for item in items:
        rec = {}
        for fname, fpath in _FIELDS.items():
            rec[fname] = _extract_field(item, list(fpath) if isinstance(fpath, list) else [fpath])
        # Add additional useful fields
        rec["cited_by_count"] = item.get("cited_by_count")
        rec["openalex_id"] = item.get("id", "").split("/")[-1] if item.get("id") else None
        results.append(rec)
    
    # Extract pagination info
    meta = data.get("meta", {})
    
    return {
        "results": results,
        "count": len(results),
        "total": meta.get("count"),
        "page": meta.get("page"),
        "per_page": meta.get("per_page"),
        "source": url
    }