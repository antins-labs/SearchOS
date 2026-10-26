"""技能目录 BM25 召回，支持英文词项和中文单字、双字词项。"""

from __future__ import annotations

import math
import re
from collections import Counter

_STOPWORDS = frozenset("a an the and or for of to in on at by with from as is are be "
                       "get find return show me please".split())

def _tokens(text: str) -> list[str]:
    tokens = []
    for part in re.findall(r"[a-z0-9]+|[\u3400-\u9fff]+", text.casefold()):
        if "\u3400" <= part[0] <= "\u9fff":
            tokens.extend(part)
            tokens.extend(part[i:i + 2] for i in range(len(part) - 1))
        elif part not in _STOPWORDS:
            tokens.append(part)
    return tokens


def shortlist(query: str, entries: list[dict], limit: int = 100) -> list[dict]:
    """返回正分候选；同分保留目录顺序。"""
    if not entries or limit <= 0:
        return []
    documents = [Counter(_tokens(_text(entry))) for entry in entries]
    lengths = [sum(document.values()) for document in documents]
    average = sum(lengths) / len(documents) or 1.0
    terms = set(_tokens(query))
    frequencies = Counter(term for document in documents for term in terms if term in document)
    scores = []
    for document, length in zip(documents, lengths):
        score = 0.0
        for term in terms:
            frequency = document[term]
            if frequency:
                idf = math.log(1 + (len(documents) - frequencies[term] + 0.5)
                               / (frequencies[term] + 0.5))
                score += idf * frequency * 2.5 / (
                    frequency + 1.5 * (0.25 + 0.75 * length / average)
                )
        scores.append(score)
    indices = sorted(range(len(entries)), key=lambda index: -scores[index])
    return [entries[index] for index in indices if scores[index] > 0][:limit]


def bilingual_shortlist(queries: dict[str, str], entries: list[dict]) -> list[dict]:
    """中英文各召回最多 50 项；交替合并并按技能名去重。"""
    zh = shortlist(queries["zh"], entries, limit=50)
    en = shortlist(queries["en"], entries, limit=50)
    ranks: dict[str, dict[str, int]] = {}
    for language, lane in (("zh", zh), ("en", en)):
        for rank, entry in enumerate(lane, 1):
            ranks.setdefault(entry["name"], {})[language] = rank
    merged, seen = [], set()
    for rank in range(max(len(zh), len(en))):
        for lane in (zh, en):
            if rank < len(lane) and lane[rank]["name"] not in seen:
                merged.append({**lane[rank], "bm25_ranks": ranks[lane[rank]["name"]]})
                seen.add(lane[rank]["name"])
    return merged


def _text(entry: dict) -> str:
    return " ".join(
        str(entry.get(field) or "")
        for field in ("name", "description", "trigger", "host")
    )
