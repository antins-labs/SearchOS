"""Coercion helpers for LLM-provided tool arguments."""

from __future__ import annotations

import json
from typing import Any


def coerce_str_list(raw: Any) -> list[str]:
    """LLM 偶尔把 list 参数编码成 JSON 字符串；直接 list(str) 会拆成单字符，
    frontier 的子集判重随之退化成字符集比较（任务被误判重复）。"""
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                raw = parsed
            elif isinstance(parsed, str):
                raw = [parsed]
            else:
                raw = [raw]
        except json.JSONDecodeError:
            raw = [raw]
    return [str(x).strip() for x in (raw or []) if str(x).strip()]
