"""保守识别抽取缺失值，不把缺失说明当成领域事实。"""

import re
from typing import Any

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
