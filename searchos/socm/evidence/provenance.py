"""来源链接、原文摘录定位与证据追溯。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from typing import Any, Optional

    from searchos.socm.evidence.graph import EvidenceNode
    from searchos.socm.state import SearchState
    from searchos.socm.storage.workspace import WorkspaceManager


def is_original_source(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https", "local"} and bool(parsed.netloc)
    except ValueError:
        return False


def source_refs(text: str) -> list[str]:
    refs = []
    for match in re.finditer(r'(?:https?://|local://|evidence:)[^\s<>\[\]`"\\]+', text or ""):
        ref = match.group().rstrip(".,;，。；")
        while ref.endswith(")") and ref.count(")") > ref.count("("):
            ref = ref[:-1]
        if ref not in refs:
            refs.append(ref)
    return refs


def result_source_urls(value) -> list[str]:
    """只传递结果声明的来源字段，排除参数、图片和任意字符串中的链接。"""
    refs = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"source_url", "source_urls", "url", "source", "canonical_url"}:
                values = item if isinstance(item, list) else [item]
                refs.extend(v for v in values if isinstance(v, str) and is_original_source(v))
            if isinstance(item, (dict, list)):
                refs.extend(result_source_urls(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(result_source_urls(item))
    return list(dict.fromkeys(refs))


def evidence_source_urls(node) -> list[str]:
    return list(
        dict.fromkeys(url for url in [node.source, *getattr(node, "source_urls", [])] if is_original_source(url))
    )


def evidence_citation(node) -> str | None:
    """Issue citations only for facts linked to original sources.

    Callers still check evidence status, answer scope, and semantic support.
    Unlinked summaries remain audit records; their IDs do not authorize citations
    or source attribution inferred from other facts."""
    return (f"evidence:{node.id}"
            if node.id and getattr(node, "status", "active") == "active" and evidence_source_urls(node)
            else None)


def select_source_urls(source, text, excerpt, requested=None, *, available=(), state=None, referring_url=""):
    """抽取器选择原文引用；仅接收本次观测已声明的地址，不猜测多来源归属。"""
    if is_original_source(source):
        # WebEvidenceMiddleware 仅为附件提供经过引用关系核对的父页面。
        return [referring_url] if referring_url in available and is_original_source(referring_url) else []
    allowed = list(dict.fromkeys([*available, *source_refs(text)]))
    if isinstance(requested, str):
        requested = [requested]
    selected = [ref for ref in (requested or []) if ref in allowed]
    if not selected:
        selected = [ref for ref in source_refs(excerpt) if ref in allowed]
    if not selected and requested is None and len(allowed) == 1 and source.startswith("skill://"):
        selected = allowed
    urls = []
    for ref in selected:
        if is_original_source(ref):
            from searchos.socm.coverage.projection import evidence_source_allowed
            from searchos.socm.evidence.graph import EvidenceNode

            if state is None or evidence_source_allowed(state, EvidenceNode(id="", source=ref)):
                urls.append(ref)
        elif ref.startswith("evidence:") and state is not None:
            from searchos.socm.coverage.projection import answer_evidence

            node = next((n for n in answer_evidence(state) if n.id == ref[9:]), None)
            if node is not None:
                urls.extend(evidence_source_urls(node))
    return list(dict.fromkeys(urls))


def resolve_answer_citations(answer, nodes):
    """解析事实引用；无法归属的内部地址显式标缺失，不伪装成原文链接。"""
    by_ref = {f"evidence:{node.id}": evidence_source_urls(node) for node in nodes}
    for node in nodes:
        if node.source.startswith(("agent://", "skill://", "edit://")):
            urls = evidence_source_urls(node)
            if node.source not in by_ref:
                by_ref[node.source] = urls
            elif by_ref[node.source] != urls:
                by_ref[node.source] = []  # 同一内部页面的不同事实不能互相代替。
    issues = []

    def resolve(ref):
        urls = by_ref.get(ref, [])
        if not urls and ref not in issues:
            issues.append(ref)
        return urls

    def link(match):
        label, ref = match.group(1), match.group(2)
        urls = resolve(ref)
        if urls:
            return " ".join(
                f"[{label if i == 0 else label + ' · ' + str(i + 1)}]({url})"
                for i, url in enumerate(urls)
            )
        if ref.startswith("evidence:") and ref not in by_ref:
            return f"[{label}](invalid-evidence-reference)"
        return f"{label}（原始来源未提供）"

    answer = re.sub(
        r"\[([^\]\n]+)\]\(((?:evidence:|agent://|skill://|edit://)[^\s)]+)\)", link, answer
    )

    def bare(match):
        ref = match.group()
        urls = resolve(ref)
        return (
            ", ".join(urls)
            if urls
            else (
                "invalid-evidence-reference"
                if ref.startswith("evidence:") and ref not in by_ref
                else "原始来源未提供"
            )
        )

    answer = re.sub(
        r"evidence:[a-zA-Z0-9_-]+|(?:agent|skill|edit)://[^\s<>\[\]`\"()]+", bare, answer
    )
    return answer, issues


_ALNUM_MIN_CHARS = 15  # below this an alnum-only match is too easy to trust


def _normalize(text: str, *, fold: bool, alnum: bool) -> tuple[str, list[int]]:
    """Collapse whitespace (or drop non-alnum); return (normalized, offsets)
    where offsets[i] is the original index of normalized char i."""
    chars: list[str] = []
    offsets: list[int] = []
    pending_space = False
    for i, ch in enumerate(text):
        if ch.isspace() or (alnum and not ch.isalnum()):
            pending_space = not alnum
            continue
        if pending_space and chars:
            chars.append(" ")
            offsets.append(offsets[-1] + 1)
        pending_space = False
        chars.append(ch.casefold() if fold else ch)
        offsets.append(i)
    return "".join(chars), offsets


def find_span(page_text: str, excerpt: str, *, browser_lines: bool = False) -> tuple[Optional[tuple[int, int]], Optional[str]]:
    """Locate *excerpt* in *page_text*; returns ((start, end), tier) or (None, None)."""
    if not page_text or not excerpt or not excerpt.strip():
        return None, None
    idx = page_text.find(excerpt)
    if idx >= 0:
        return (idx, idx + len(excerpt)), "exact"

    for tier, fold, alnum in (("ws", False, False), ("ws_fold", True, False), ("alnum", True, True)):
        norm_page, offsets = _normalize(page_text, fold=fold, alnum=alnum)
        norm_ex, _ = _normalize(excerpt, fold=fold, alnum=alnum)
        if not norm_ex or (alnum and len(norm_ex) < _ALNUM_MIN_CHARS):
            continue
        j = norm_page.find(norm_ex)
        if j >= 0:
            return (offsets[j], offsets[j + len(norm_ex) - 1] + 1), tier
    if browser_lines:
        # 匹配时移除浏览器行号，返回位置仍按带行号的原文计数。
        chars, offsets = [], []
        end = 0
        for match in re.finditer(r"(?m)^L\d+: ", page_text):
            chars.append(page_text[end:match.start()])
            offsets.extend(range(end, match.start()))
            end = match.end()
        if end:
            chars.append(page_text[end:])
            offsets.extend(range(end, len(page_text)))
            span, tier = find_span("".join(chars), excerpt)
            if span is not None:
                return (offsets[span[0]], offsets[span[1] - 1] + 1), f"browser_{tier}"
    return None, None


def _trace_node(node: EvidenceNode, ws: WorkspaceManager | None, state: SearchState) -> dict[str, Any]:
    raw_snippet = node.source_excerpt or ""
    # 优先使用抽取时保存的坐标；旧记录缺失时再从保存页面定位。
    span_obj: dict[str, int] | None = None
    if node.span is not None:
        span_obj = {"start_char": node.span[0], "end_char": node.span[1]}
    elif raw_snippet and ws and node.page_id:
        page_text = ws.read_page(node.page_id)
        idx = page_text.find(raw_snippet) if page_text else -1
        if idx >= 0:
            span_obj = {"start_char": idx, "end_char": idx + len(raw_snippet)}
    observation = next((item for item in state.evidence_graph.observations
                        if item.id == node.observation_id and item.source == node.source), None)
    if node.observation_id:
        # 来源观测的坐标始终相对于该观测窗口。
        span_obj = None
        if observation is not None and node.span is not None:
            start, end = node.span
            if 0 <= start <= end <= len(observation.text) and observation.text[start:end] == raw_snippet:
                span_obj = {"start_char": start, "end_char": end}
    return {
        "evidence_id": node.id,
        "page_id": node.page_id,
        "source_url": node.source,
        "source_urls": evidence_source_urls(node),
        "snippet": raw_snippet,
        "span": span_obj,
        "span_basis": "observation" if node.observation_id else "page",
        "observation_id": node.observation_id,
        "observation_text_hash": observation.text_hash if observation else "",
        "text_hash": node.text_hash,
        "finding": node.finding,
        "confidence": node.confidence,
    }


def resolve_cell_provenance(
    state: SearchState,
    *,
    cell: str | None = None,
    evidence_id: str | None = None,
    workspace: WorkspaceManager | None = None,
) -> list[dict[str, Any]]:
    """按单元格或证据 ID 返回已授权事实的原文片段与坐标。"""
    if (cell is None) == (evidence_id is None):
        raise ValueError("exactly one of `cell` or `evidence_id` is required")

    from searchos.socm.coverage import evidence_source_allowed, project_cell_evidence
    from searchos.socm.refs import cell_ref
    nodes_by_id = {n.id: n for n in state.evidence_graph.nodes if evidence_source_allowed(state, n)}

    if evidence_id is not None:
        node = nodes_by_id.get(evidence_id)
        return [_trace_node(node, workspace, state)] if node else []

    ids = state.coverage_map.cells.get(cell, None)
    if ids is None:
        return []
    target = state.coverage_map.cell_binding(cell)
    if target is None:
        return []
    return [
        {**_trace_node(view, workspace, state), "cell": cell_ref(cell), "cell_value": view.value}
        for eid in ids.supporting_evidence_ids
        if eid in nodes_by_id
        and (view := project_cell_evidence(state.coverage_map, nodes_by_id[eid], *target)) is not None
    ]
