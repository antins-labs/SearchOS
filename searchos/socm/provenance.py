"""保留观测身份，按事实解析原文链接；可追溯不等于语义已核验。"""

from __future__ import annotations

import re
from urllib.parse import urlsplit


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
    if is_original_source(node.source):
        return [node.source]
    return list(
        dict.fromkeys(url for url in getattr(node, "source_urls", []) if is_original_source(url))
    )


def select_source_urls(source, text, excerpt, requested=None, *, available=(), state=None):
    """抽取器选择原文引用；仅接收本次观测已声明的地址，不猜测多来源归属。"""
    if is_original_source(source):
        return []  # 原文观测直接使用 source，不复制字段。
    allowed = list(dict.fromkeys([*available, *source_refs(text)]))
    if isinstance(requested, str):
        requested = [requested]
    selected = [ref for ref in (requested or []) if ref in allowed]
    if not selected:
        selected = [ref for ref in source_refs(excerpt) if ref in allowed]
    if not selected and requested is None and len(allowed) == 1:
        selected = allowed
    urls = []
    for ref in selected:
        if is_original_source(ref):
            from searchos.socm.coverage import evidence_source_allowed
            from searchos.socm.evidence import EvidenceNode

            if state is None or evidence_source_allowed(state, EvidenceNode(id="", source=ref)):
                urls.append(ref)
        elif ref.startswith("evidence:") and state is not None:
            from searchos.socm.coverage import answer_evidence

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
