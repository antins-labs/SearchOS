"""清理阅读窗口、保留同源上下文，并按输入预算切片。"""

from __future__ import annotations

import json
from typing import Any

from searchos.harness.middleware.extraction.core.models import ExtractionConfig
from searchos.harness.middleware.extraction.core.tables.prompts import _render_pages_block


class ObservationPreparer:
    """每个协调器独享的窗口历史；不调用模型、不写入证据。"""

    def __init__(self, config: ExtractionConfig, trajectory_logger: Any = None) -> None:
        self._config = config
        self._trajectory_logger = trajectory_logger
        self._source_window_history: dict[tuple, list[dict[str, Any]]] = {}

    @staticmethod
    def _strip_extraction_noise(text: str) -> str:
        """Strip the search-agent's render scaffolding (show_page header,
        L<N>: line prefixes, END OF PAGE footer). Markdown link sugar
        is left intact — regex strip breaks on URLs with escaped parens."""
        import re

        if text.startswith("[Now viewing local source]") and "\n\n" in text:
            return text.split("\n\n", 1)[1]
        if text.startswith("[Now viewing]") and "\n\n" in text:
            # URL / Page ID / 视窗范围来自阅读工具标题；保留它们会使完整 JSON
            # 无法解析，进而失去记录计数与结构化切片。
            text = text.split("\n\n", 1)[1]

        out: list[str] = []
        for line in text.split("\n"):
            stripped = line.lstrip()
            if (
                stripped.startswith("[Now viewing]")
                or stripped.startswith("URL: ")
                or stripped.startswith("**viewing lines")
                or stripped.startswith("[END OF PAGE")
            ):
                continue
            m = re.match(r"^L\d+:\s?", line)
            if m:
                line = line[m.end() :]
            out.append(line)
        return "\n".join(out)

    def _clean_window(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            **item,
            "content": self._strip_extraction_noise(item.get("content", "") or ""),
            "observation_text": item.get("observation_text", item.get("content", "") or ""),
            "content_hashes": [item["content_hash"]] if item.get("content_hash") else [],
        }

    def original_windows(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._clean_window(item) for item in items]

    def prepare_pages(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Clean pages and attach bounded same-source context.

        URL/size-triggered batches can still split a long page across flushes.
        Keep a rolling history on this per-sub-agent Extraction so a continuation
        can see the preceding table rows/header. Only web PAGE observations
        participate; agent summaries, local documents, findings and skills
        retain their original semantics.
        """
        grouped: dict[tuple, list[dict[str, Any]]] = {}
        agent_items: list[dict[str, Any]] = []
        for it in items:
            url = it.get("source_url", "") or ""
            content = self._strip_extraction_noise(it.get("content", "") or "")
            hashes = [h for h in [it.get("content_hash", "")] if h]
            target_table = it.get("target_table", "") or ""
            local_source_metadata = it.get("local_source_metadata")
            source_kind = str(it.get("source_kind", "") or "")
            if (
                url.startswith(("agent://", "local://"))
                or (source_kind and source_kind != "page")
            ):
                agent_items.append(self._clean_window(it))
                continue
            cleaned = {
                **it,
                "source_url": url,
                "content": content,
                "content_hashes": list(hashes),
                "target_table": target_table,
                "local_source_metadata": local_source_metadata,
            }
            group_key = (self._scope_key(it), url, tuple(it.get("referring_page") or ()))
            grouped.setdefault(group_key, []).append(cleaned)

        prepared: list[dict[str, Any]] = []
        for (scope, url, parent), current in grouped.items():
            first = current[0]
            key = (
                scope,
                url,
                parent,
            )
            current_hashes = list(
                dict.fromkeys(h for item in current for h in item.get("content_hashes", []) if h)
            )
            current_hash_set = set(current_hashes)
            prior = [
                item
                for item in self._source_window_history.get(key, [])
                if item.get("content_hash") not in current_hash_set
            ]
            selected_prior = self._select_source_context(prior, current)
            windows = selected_prior + current
            if len(windows) == 1:
                merged_content = windows[0]["content"]
            else:
                parts = []
                prior_count = len(selected_prior)
                for index, window in enumerate(windows):
                    role = "retained context" if index < prior_count else "current viewport"
                    parts.append(f"--- ({role} on same page) ---\n{window['content']}")
                merged_content = "\n\n".join(parts)
            prepared.append(
                {
                    **first,
                    "content": merged_content,
                    "observation_text": merged_content,
                    # Settle only observations in this flush. Historical hashes
                    # may already be committed and must not be released on a later
                    # parse failure.
                    "content_hashes": current_hashes,
                }
            )
            self._remember_source_windows(key, prior + current)
        return prepared + agent_items

    def _select_source_context(
        self,
        prior: list[dict[str, Any]],
        current: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Choose the newest prior windows that fit beside this flush."""
        max_windows = max(0, int(self._config.source_context_max_windows))
        budget = min(
            max(0, int(self._config.source_context_char_budget)),
            max(0, int(self._config.chunk_char_budget)),
        )
        if max_windows == 0 or budget == 0:
            return []
        remaining_windows = max(0, max_windows - len(current))
        remaining_chars = max(0, budget - sum(len(it.get("content", "") or "") for it in current))
        chosen: list[dict[str, Any]] = []
        for item in reversed(prior):
            content = item.get("content", "") or ""
            if len(chosen) >= remaining_windows or len(content) > remaining_chars:
                break
            chosen.append(item)
            remaining_chars -= len(content)
        chosen.reverse()
        return chosen

    def _remember_source_windows(
        self,
        key: tuple,
        windows: list[dict[str, Any]],
    ) -> None:
        """Store a deduplicated, bounded tail for this agent/source."""
        unique: list[dict[str, Any]] = []
        positions: dict[str, int] = {}
        for item in windows:
            content_hash = str(item.get("content_hash", "") or "")
            if content_hash and content_hash in positions:
                unique[positions[content_hash]] = item
            else:
                if content_hash:
                    positions[content_hash] = len(unique)
                unique.append(item)
        max_windows = max(0, int(self._config.source_context_max_windows))
        budget = min(
            max(0, int(self._config.source_context_char_budget)),
            max(0, int(self._config.chunk_char_budget)),
        )
        kept: list[dict[str, Any]] = []
        chars = 0
        for item in reversed(unique):
            content = item.get("content", "") or ""
            if len(kept) >= max_windows or chars + len(content) > budget:
                break
            kept.append(item)
            chars += len(content)
        kept.reverse()
        if kept:
            self._source_window_history[key] = kept
        else:
            self._source_window_history.pop(key, None)

    @staticmethod
    def _source_domain(item: dict[str, Any]) -> str:
        """Group key for exec packing: host for http(s), scheme+path head otherwise."""
        from urllib.parse import urlparse

        url = str(item.get("source_url") or "")
        if not url:
            return ""
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return parsed.netloc.lower()
        if parsed.scheme:
            return f"{parsed.scheme}://{(parsed.netloc or parsed.path.split('/', 1)[0]).lower()}"
        return url.lower()

    def pack_items(
        self,
        items: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        """按来源域名分组后再按范围与累计预算分包，保留对象、正文和哈希供独立结算。

        单份超预算观察独立成包，由 chunk_items 切片或明确报错。
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        for item in items:
            domain = self._source_domain(item)
            if domain not in grouped:
                order.append(domain)
                grouped[domain] = []
            grouped[domain].append(item)
        packages: list[list[dict[str, Any]]] = []
        for domain in order:
            packages.extend(self._pack_budget(grouped[domain]))
        return packages

    def _pack_budget(self, items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        limit = min(5, max(1, self._config.max_sources_per_call))
        packages: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        records = 0
        for item in items:
            count = self._count_structured_records(item.get("content", "") or "") or 0
            if current and (
                len(current) >= limit
                or records + count > self._config.chunk_max_records
                or len(_render_pages_block([*current, item])) > self._config.chunk_char_budget
                or self._scope_key(current[0]) != self._scope_key(item)
                or any(self._same_skill_source(previous, item) for previous in current)
            ):
                packages.append(current)
                current, records = [], 0
            current.append(item)
            records += count
        if current:
            packages.append(current)
        return packages

    @staticmethod
    def _same_skill_source(left: dict[str, Any], right: dict[str, Any]) -> bool:
        """同一技能页的多个阅读窗口独立调用，保留完整 JSON 与局部窗口边界。"""
        if not any(
            str(item.get("source_kind", "")) == "skill"
            or str(item.get("source_url", "")).startswith("skill://")
            for item in (left, right)
        ):
            return False
        return any(
            left.get(key) and left.get(key) == right.get(key)
            for key in ("source_url", "page_id")
        )

    @staticmethod
    def _scope_key(item: dict[str, Any]) -> tuple:
        return (
            item.get("task_id", "") or "",
            item.get("target_table", "") or "",
            item.get("task_target_table", "") or "",
            frozenset(item.get("task_target_cells") or ()),
            bool(item.get("all_schema_targets")),
        )

    def chunk_items(
        self,
        items: list[dict[str, Any]],
    ) -> list[list[dict[str, Any]]]:
        """切片过长来源，再按请求预算分包。"""
        budget = self._config.chunk_char_budget
        max_records = self._config.chunk_max_records
        segments: list[dict[str, Any]] = []
        for item in items:
            overhead = len(_render_pages_block([{**item, "content": ""}]))
            content_budget = budget - overhead
            content = item.get("content", "") or ""
            if (
                len(content) <= content_budget
                and (self.count_records_in_items([item]) or 0) <= max_records
            ):
                segments.append(item)
            else:
                segments.extend(
                    self._split_oversized_item(item, content_budget, max_records=max_records)
                )
        return self.pack_items(segments)

    def _split_oversized_item(
        self,
        item: dict[str, Any],
        budget: int,
        *,
        max_records: int,
    ) -> list[dict[str, Any]]:
        """保留合法 JSON 的记录边界；普通文本按窗口切片并继承原文与哈希。"""
        content = item.get("content", "") or ""
        url = item.get("source_url", "") or ""
        hashes = list(item.get("content_hashes") or [])
        target_table = item.get("target_table", "") or ""
        if budget <= 0:
            raise ValueError(
                f"extraction_input_exceeds_budget: {url}: page context exceeds character budget"
            )
        segs = self._split_skill_json(content, budget, max_records=max_records)
        if segs is None:
            header = self._context_header(content, url)
            segs = self._split_by_chars(content, budget, header=header)
        if any(
            len(segment) > budget or (self._count_structured_records(segment) or 0) > max_records
            for segment in segs
        ):
            raise ValueError(
                f"extraction_input_exceeds_budget: {url}: indivisible JSON record or page context"
            )
        if self._trajectory_logger and len(segs) > 1:
            self._trajectory_logger._append_raw(
                {
                    "type": "harness",
                    "kind": "extraction_input_split",
                    "source": url[:200],
                    "orig_chars": len(content),
                    "segments": len(segs),
                }
            )
        return [
            {
                "source_url": url,
                **item,
                "content": s,
                "content_hashes": hashes,
                "target_table": target_table,
            }
            for s in segs
        ]

    @staticmethod
    def _split_skill_json(
        content: str,
        budget: int,
        *,
        max_records: int,
    ) -> list[str] | None:
        """按最长顶层数组切片，并为完整 JSON 和分片元数据预留字符预算。"""
        if not content.lstrip().startswith(("{", "[")):
            return None
        try:
            data = json.loads(content)
        except (TypeError, ValueError):
            return None

        def chunk_meta(
            *,
            split_field: str,
            chunk_index: int,
            chunk_count: int,
            record_start: int,
            records_in_chunk: int,
            total_records: int,
        ) -> dict[str, Any]:
            return {
                "split_field": split_field,
                "chunk_index": chunk_index,
                "chunk_count": chunk_count,
                "record_start_1based": record_start,
                "record_end_1based": record_start + records_in_chunk - 1,
                "records_in_chunk": records_in_chunk,
                "total_records": total_records,
            }

        if isinstance(data, list):
            array_key, rows, meta, split_field = "records", data, {}, "<root>"
        elif isinstance(data, dict):
            arrays = [(key, value) for key, value in data.items() if isinstance(value, list)]
            if not arrays:
                return [content]
            array_key, rows = max(arrays, key=lambda pair: len(pair[1]))
            meta = {key: value for key, value in data.items() if key != array_key}
            split_field = str(array_key)
        else:
            return [content]
        if len(rows) <= 1:
            return [content]
        total_records = len(rows)

        def encode(group: list[Any], index: int, count: int, start: int) -> str:
            return json.dumps({
                **meta,
                "_searchos_chunk": chunk_meta(
                    split_field=split_field,
                    chunk_index=index,
                    chunk_count=count,
                    record_start=start,
                    records_in_chunk=len(group),
                    total_records=total_records,
                ),
                array_key: group,
            }, ensure_ascii=False)

        groups: list[list[Any]] = []
        cur: list[Any] = []
        for row in rows:
            candidate = [*cur, row]
            # 最大分片编号预留足够位数，最终编号只会缩短序列化结果。
            if cur and (
                len(candidate) > max_records
                or len(encode(candidate, total_records, total_records, total_records)) > budget
            ):
                groups.append(cur)
                cur = []
            cur.append(row)
        if cur:
            groups.append(cur)
        if len(groups) <= 1:
            return [content]
        chunk_count = len(groups)
        segs: list[str] = []
        record_start = 1
        for idx, group in enumerate(groups, start=1):
            segs.append(encode(group, idx, chunk_count, record_start))
            record_start += len(group)
        return segs

    @classmethod
    def count_records_in_chunks(
        cls,
        chunks: list[list[dict[str, Any]]],
    ) -> int | None:
        counts = [cls.count_records_in_items(chunk) for chunk in chunks]
        counts = [c for c in counts if c is not None]
        return sum(counts) if counts else None

    @classmethod
    def count_records_in_items(
        cls,
        items: list[dict[str, Any]],
    ) -> int | None:
        counts = [cls._count_structured_records(item.get("content", "") or "") for item in items]
        counts = [c for c in counts if c is not None]
        return sum(counts) if counts else None

    @staticmethod
    def _count_structured_records(content: str) -> int | None:
        """Best-effort count of records inside a structured skill payload.

        Prefer the longest top-level array length. For split skill JSON this
        counts the per-chunk array length (e.g. 50 + 50), not metadata such as
        ``items_count=100`` duplicated into every segment.
        """
        if not content.lstrip().startswith(("{", "[")):
            return None
        try:
            data = json.loads(content)
        except Exception:
            return None
        if isinstance(data, list):
            return len(data)
        if not isinstance(data, dict):
            return None
        array_lens = [len(value) for value in data.values() if isinstance(value, list)]
        if array_lens:
            return max(array_lens)
        for key in ("items_count", "total_items", "count", "total"):
            value = data.get(key)
            if isinstance(value, int) and value >= 0:
                return value
        return None

    @staticmethod
    def _context_header(content: str, url: str) -> str:
        """Best-effort metadata header to prepend onto char-split segments.

        For a JSON-ish payload the top-level metadata precedes the first array,
        so everything up to the first ``[`` is the header (capped). Falls back
        to a source_url line. Empty when neither applies. Char segments are
        already invalid JSON, so this is context for the judge, not valid JSON.
        """
        s = content.lstrip()
        if s.startswith("{"):
            i = content.find("[")
            if 0 < i <= 2000:
                head = content[:i].rstrip().rstrip(",").rstrip()
                if head:
                    return head
        if url:
            return f'{{"source_url": "{url}"}}'
        return ""

    def _split_by_chars(self, content: str, budget: int, header: str = "") -> list[str]:
        """Fallback split into budget-sized windows, cutting on a newline near
        the window end when possible and overlapping segments slightly so a
        record straddling a cut survives in at least one segment. Every segment
        after the first is prefixed with ``header`` (the leading metadata) so it
        keeps province/year/url context — the head budget shrinks to compensate
        so a segment+header still fits."""
        overlap = max(0, self._config.chunk_overlap_chars)
        n = len(content)
        if n <= budget:
            return [content]
        prefix = (header + "\n") if header else ""
        body_budget = budget - len(prefix)
        if body_budget <= 0:
            raise ValueError(
                "extraction_input_exceeds_budget: continuation header exceeds character budget"
            )
        overlap = min(overlap, max(0, body_budget - 1))
        segs: list[str] = []
        start = 0
        while start < n:
            end = min(n, start + body_budget)
            if end < n:
                nl = content.rfind("\n", start + int(body_budget * 0.9), end)
                if nl > start:
                    end = nl
            body = content[start:end]
            segs.append(body if not segs else prefix + body)
            if end >= n:
                break
            start = max(end - overlap, start + 1)
        return segs


_UNEXTRACTABLE_PATTERNS = (
    "404 not found",
    "page not found",
    "页面不存在",
    "页面未找到",
    "403 forbidden",
    "access denied",
    "permission denied",
    "please sign in",
    "please log in",
    "login required",
    "请登录",
    "cloudflare",
    "are you human",
    "verify you are human",
    "captcha",
    "just a moment...",
    "service unavailable",
    "503 service",
)


def is_extractable_page(content: str) -> bool:
    """False on clearly-error / auth-wall / captcha stubs or body
    shorter than a sentence. Conservative — borderline pages still
    reach the judge."""
    if not content:
        return False
    body = content
    header_end = body.find("\n")
    if header_end > 0 and header_end < 300:
        body = body[header_end + 1 :]
    if len(body.strip()) < 80:
        return False
    lower = content.lower()
    for pat in _UNEXTRACTABLE_PATTERNS:
        if pat in lower:
            # Require the marker in the first 600 chars (where error
            # pages put their headline) — a long article that just
            # mentions "captcha" in passing shouldn't be filtered.
            if lower.find(pat) < 600:
                return False
    return True


class OriginalWindowPreparer(ObservationPreparer):
    """逐个保留原始观察，不合并跨次阅读的上下文。"""

    def prepare_pages(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.original_windows(items)
