"""重复查询检测的文本归一化。"""

import re


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s:\-./]", " ", query.lower())).strip()
