"""保守识别抽取缺失值，不把缺失说明当成领域事实。"""

from __future__ import annotations

import re
from typing import Any

# 候选行的主键只过滤完整空值标记，保留数组文本和缺失说明的原有语义。
_NULL_VALUES = {"", "none", "null", "n/a", "/", "-", "–", "—", "--"}
_EMPTY = {"", "none", "null", "n/a", "/", "-", "–", "—", "--", "[]", "{}"}
_ABSENCE = re.compile(
    r"^(?:the\s+(?:(?:provided|current|source)\s+)?page\s+does\s+not\s+"
    r"(?:contain|provide|mention)\b|(?:该|当前|所提供的)页面(?:未|没有)(?:提供|包含|提及))",
    re.IGNORECASE,
)


def is_missing_value(value: Any) -> bool:
    """空容器是未提供值；明确的领域否定句仍保留为证据。"""
    if value is None or isinstance(value, (list, tuple, dict)) and not value:
        return True
    text = str(value).strip()
    return text.lower() in _EMPTY or bool(_ABSENCE.match(text))


def is_null_marker(value: Any) -> bool:
    """主键校验用的空值/占位标记（含 ``/``）。"""
    if value is None:
        return True
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return True
    return str(value).strip().lower() in _NULL_VALUES


def normalize_pk_field(value: Any) -> str:
    """主键字段归一：缺失标记统一写成 ``/``。"""
    if is_null_marker(value):
        return "/"
    return str(value).strip()


def has_non_placeholder_pk(row: dict[str, Any], primary_key: list[str] | tuple[str, ...]) -> bool:
    """复合主键有效当且仅当至少一个主键字段不是缺失标记。"""
    return any(not is_null_marker(row.get(key)) for key in primary_key)
