"""itunes_media_item — agent-called public-API access skill (auto-generated)."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from searchos.skills.core.contract import SkillContext

logger = logging.getLogger(__name__)

_URL_TEMPLATE = 'https://itunes.apple.com/search?term={term}&entity={entity}&limit={limit}'
_HEADERS = {'Accept': 'application/json'}
_RESULT_PATH = ['results']
_FIELDS = {'title': ['collectionName'], 'artist': ['artistName'], 'url': ['collectionViewUrl'], 'genre': ['primaryGenreName'], 'release_date': ['releaseDate']}


def _walk(obj: Any, path: list[str]) -> Any:
    for key in path:
        if isinstance(obj, dict):
            obj = obj.get(key)
        else:
            return None
    return obj


def _extract_field(item: Any, path: list[str]) -> Any:
    val = _walk(item, path) if path else item
    if isinstance(val, list):
        return [str(v) for v in val if v is not None]
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val)[:500]
    return str(val)[:2000]


async def execute(params: dict[str, Any], ctx: SkillContext) -> dict[str, Any]:
    url = _URL_TEMPLATE
    for k, v in params.items():
        url = url.replace("{" + k + "}", str(v))
    timeout = aiohttp.ClientTimeout(total=25.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.get(url, headers=_HEADERS) as resp:
                if resp.status >= 400:
                    return {"error": f"http_{resp.status}", "url": url}
                body = await resp.read()
        except Exception as e:  # noqa: BLE001
            return {"error": f"fetch_{type(e).__name__}: {e}", "url": url}
    try:
        data = json.loads(body)
    except Exception as e:  # noqa: BLE001
        return {"error": f"json_decode: {e}", "url": url}

    items = _walk(data, list(_RESULT_PATH)) if _RESULT_PATH else data
    if items is None:
        return {"error": "result_path_miss", "keys": list(data.keys()) if isinstance(data, dict) else None}
    if not isinstance(items, list):
        items = [items]

    num = int(params.get("num_results", 5) or 5)
    items = items[:max(1, num)]
    results = []
    for item in items:
        rec = {}
        for fname, fpath in _FIELDS.items():
            rec[fname] = _extract_field(item, list(fpath) if isinstance(fpath, list) else [fpath])
        results.append(rec)
    return {"results": results, "count": len(results), "source": url}
