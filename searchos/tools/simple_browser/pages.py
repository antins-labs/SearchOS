"""页面模型、HTML/JSON 渲染与页内匹配。"""

from __future__ import annotations

import difflib
import json
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import html2text
import lxml.etree
import lxml.html

from searchos.tools.simple_browser.search_providers.base import SearchResult

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Extract:
    """A search result snippet or quotable extract."""

    url: str
    text: str
    title: str = ""
    line_idx: int | None = None


@dataclass
class PageContents:
    """Unified page representation: search results page OR normal web page."""

    url: str
    title: str = ""
    text: str = ""
    urls: dict[str, str] = field(default_factory=dict)       # link_id → url
    snippets: dict[str, Extract] | None = None               # for search results
    source_url: str = ""  # 派生阅读视图的原始来源；普通页面使用 url。
    metadata: dict = field(default_factory=dict)  # Host-owned page classification/provenance.


# ---------------------------------------------------------------------------
# HTML processing (full lxml version)
# ---------------------------------------------------------------------------

HTML_SUP_RE = re.compile(r"<sup( [^>]*)?>([\w\-]+)</sup>")
HTML_SUB_RE = re.compile(r"<sub( [^>]*)?>([\w\-]+)</sub>")
HTML_TAGS_SEQ_RE = re.compile(r"(?<=\w)((<[^>]*>)+)(?=\w)")
EMPTY_LINE_RE = re.compile(r"^\s+$", flags=re.MULTILINE)
EXTRA_NEWLINE_RE = re.compile(r"\n(\s*\n)+")

_SPECIAL_CHAR_REPLACEMENTS = {
    "【": "〖",  # 【 → 〖
    "】": "〗",  # 】 → 〗
    "◼": "◾",  # ◼ → ◾
    "​": "",        # zero width space
}


def _get_domain(url: str) -> str:
    if "http" not in url:
        url = "http://" + url
    return urlparse(url).netloc


def _replace_special_chars(text: str) -> str:
    regex = re.compile("(%s)" % "|".join(map(re.escape, _SPECIAL_CHAR_REPLACEMENTS.keys())))
    return regex.sub(lambda mo: _SPECIAL_CHAR_REPLACEMENTS[mo.group(1)], text)


def _merge_whitespace(text: str) -> str:
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text)


def _get_text(node: lxml.html.HtmlElement) -> str:
    return _merge_whitespace(" ".join(node.itertext()))


def _replace_node_with_text(node: lxml.html.HtmlElement, text: str) -> None:
    previous = node.getprevious()
    parent = node.getparent()
    tail = node.tail or ""
    if previous is None:
        parent.text = (parent.text or "") + text + tail
    else:
        previous.tail = (previous.tail or "") + text + tail
    parent.remove(node)


def _clean_links(root: lxml.html.HtmlElement, cur_url: str) -> dict[str, str]:
    """Extract and number all anchor tags. Replace each <a> with 【id†text†domain】."""
    cur_domain = _get_domain(cur_url) if cur_url else ""
    urls: dict[str, str] = {}
    urls_rev: dict[str, str] = {}

    for a in root.findall(".//a[@href]"):
        if a.getparent() is None:
            continue
        link = a.attrib["href"]
        if link.startswith(("mailto:", "javascript:")):
            continue

        text = _get_text(a).replace("†", "‡")  # † → ‡
        if not text:
            continue
        if link.startswith("#"):
            _replace_node_with_text(a, text)
            continue

        try:
            link = urljoin(cur_url, link)
            domain = _get_domain(link)
        except Exception:
            domain = ""
        if not domain:
            continue

        if (link_id := urls_rev.get(link)) is None:
            link_id = f"{len(urls)}"
            urls[link_id] = link
            urls_rev[link] = link_id

        if domain == cur_domain:
            replacement = f"【{link_id}†{text}】"
        else:
            replacement = f"【{link_id}†{text}†{domain}】"
        _replace_node_with_text(a, replacement)

    return urls


def _replace_images(root: lxml.html.HtmlElement, cur_url: str) -> None:
    cnt = 0
    for img_tag in root.findall(".//img"):
        image_name = img_tag.get("alt", img_tag.get("title"))
        replacement = f"[Image {cnt}: {image_name}]" if image_name else f"[Image {cnt}]"
        source = (img_tag.get("src") or "").strip()
        if source:
            image_url = urljoin(cur_url, source)
            if urlparse(image_url).scheme in {"http", "https"}:
                replacement += f" {image_url} "
        _replace_node_with_text(img_tag, replacement)
        cnt += 1


_NUMBERED_LINK = re.compile(r"【(\d+)†([^】]*)】")


def _is_attachment_link(url: str, label: str = "") -> bool:
    return url.startswith(("https://", "http://")) and bool(
        re.search(r"\.(?:pdf|png|jpe?g|gif|webp|bmp|tiff?)$", url.partition("?")[0].partition("#")[0], re.I)
        or re.search(r"\bpdf\b", label.split("†", 1)[0], re.I)
    )


def visible_attachment_urls(text: str, links: dict[str, str]) -> list[str]:
    """从当前阅读窗口解析图片和 PDF 的实际链接。"""
    from searchos.socm.evidence.provenance import source_refs

    refs = source_refs(text)
    attachments = [url for url in refs if _is_attachment_link(url)]
    attachments.extend(links[i] for i, label in _NUMBERED_LINK.findall(text)
                       if i in links and _is_attachment_link(links[i], label))
    attachments.extend(re.findall(r"\[attachment\]\(<(https?://[^\s>]+)>\)", text))
    # 图片地址可以使用不带扩展名的下载接口。
    for match in re.finditer(r"(?:\[Image \d+[^\]]*\]\s*\(?|!\[[^\]]*\]\(|"
                             r"\[[^\]]*\bpdf\b[^\]]*\]\()\s*(https?://[^\s)]+)", text, re.I):
        attachments.append(match.group(1))
    return list(dict.fromkeys(attachments))


def _remove_math(root: lxml.html.HtmlElement) -> None:
    for node in root.findall(".//math"):
        node.getparent().remove(node)


def _remove_unicode_smp(text: str) -> str:
    return re.sub(r"[\U00010000-\U0001FFFF]", "", text, flags=re.UNICODE)


def _html_to_text(html: str) -> str:
    """Convert HTML to clean plaintext with html2text, preserving our link format."""
    html = re.sub(HTML_SUP_RE, r"^{\2}", html)
    html = re.sub(HTML_SUB_RE, r"_{\2}", html)
    html = re.sub(HTML_TAGS_SEQ_RE, r" \1", html)

    orig_escape_md = html2text.utils.escape_md
    orig_escape_md_section = html2text.utils.escape_md_section
    html2text.utils.escape_md = lambda text, snob=False: text
    html2text.utils.escape_md_section = lambda text, snob=False: text

    try:
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.body_width = 0
        h.ignore_tables = True
        h.unicode_snob = True
        h.ignore_emphasis = True
        return h.handle(html).strip()
    finally:
        html2text.utils.escape_md = orig_escape_md
        html2text.utils.escape_md_section = orig_escape_md_section


def process_html(html: str, url: str, title: str | None = None) -> PageContents:
    """Convert raw HTML into model-readable PageContents with numbered links."""
    html = _remove_unicode_smp(html)
    html = _replace_special_chars(html)
    try:
        root = lxml.html.fromstring(html)
    except Exception:
        # Fallback for malformed HTML
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return PageContents(url=url, title=title or _get_domain(url), text=text, urls={})

    title_element = root.find(".//title")
    final_title = (
        title
        or (title_element.text if title_element is not None and title_element.text else None)
        or (_get_domain(url) if url else "")
        or ""
    )

    _replace_images(root, url)
    urls = _clean_links(root, url)
    _remove_math(root)

    clean_html = lxml.etree.tostring(root, encoding="UTF-8").decode()
    text = _html_to_text(clean_html)

    text = re.sub(EMPTY_LINE_RE, "", text)
    text = re.sub(EXTRA_NEWLINE_RE, "\n\n", text)

    top = f"URL: {url}\n\n" if url else ""
    return PageContents(url=url, title=final_title.strip(), text=top + text, urls=urls)


# ---------------------------------------------------------------------------
# Display utilities (line wrapping / truncation / anchor text)
# ---------------------------------------------------------------------------

def _wrap_lines(text: str, width: int = 80, *, links: dict[str, str] | None = None) -> list[str]:
    if links:
        def expand(match: re.Match) -> str:
            url = links.get(match[1], "")
            if _is_attachment_link(url, match[2]) and url not in match[2]:
                return f"{match[0]} [attachment](<{url}>)"
            return match[0]

        text = _NUMBERED_LINK.sub(expand, text)
    lines = text.split("\n")
    wrapped: list[str] = []
    for line in lines:
        if line:
            wrapped.extend(
                textwrap.wrap(
                    line,
                    width=width,
                    replace_whitespace=False,
                    drop_whitespace=False,
                    break_long_words=False,
                    break_on_hyphens=False,
                )
            )
        else:
            wrapped.append("")
    return wrapped


def _extract_link_text(match: re.Match) -> str:
    """Extract display text from a 【id†text†domain】 anchor."""
    content = match.group(0)
    inner = content[1:-1]
    parts = inner.split("†")
    return parts[1] if len(parts) >= 2 else inner


def _build_search_page(query: str, results: list[SearchResult]) -> PageContents:
    """Build a PageContents from raw search results, preserving snippets."""
    if not results:
        return PageContents(
            url="search://empty",
            title=f"Search: {query}",
            text=f"No results for: {query}",
            urls={}, snippets={},
        )

    urls: dict[str, str] = {}
    snippets: dict[str, Extract] = {}
    lines = [f"Search: {query} ({len(results)} results)\n"]

    for i, r in enumerate(results):
        link_id = str(i)
        urls[link_id] = r.url
        lines.append(f"[{link_id}] {r.url}")
        if r.title:
            lines.append(f"    {r.title}")
        if r.snippet:
            lines.append(f"    {r.snippet}")
        lines.append("")
        snippets[link_id] = Extract(url=r.url, text=r.snippet, title=r.title)

    return PageContents(
        url="search://results",
        title=f"Search: {query}",
        text="\n".join(lines),
        urls=urls,
        snippets=snippets,
    )


_TOKEN_RE = re.compile(r"[A-Za-z一-鿿][A-Za-z0-9一-鿿'_-]{2,}")


def _fuzzy_hint(patterns: list[str], search_lines: list[str], k: int = 3) -> str:
    """For each missed pattern, surface the top-k closest tokens on the page.

    Returns a multi-line hint or empty string. Uses difflib (stdlib).
    The signal lets the LLM see "no exact hit, but the page has X / Y / Z"
    instead of giving up and re-issuing a near-duplicate find.
    """
    vocab: dict[str, int] = {}
    for li, ln in enumerate(search_lines):
        for tok in _TOKEN_RE.findall(ln):
            tl = tok.lower()
            if tl not in vocab:
                vocab[tl] = li
    if not vocab:
        return ""
    keys = list(vocab.keys())
    blocks: list[str] = []
    for p in patterns:
        pl = p.lower().strip()
        if not pl:
            continue
        cand = difflib.get_close_matches(pl, keys, n=k, cutoff=0.7)
        if not cand:
            continue
        items = ", ".join(f"`{c}` (L{vocab[c]})" for c in cand)
        blocks.append(f"  - `{p}` -> near-tokens: {items}")
    if not blocks:
        return ""
    return "[FUZZY] No exact match; closest tokens on page:\n" + "\n".join(blocks)


def _find_matches(
    pattern,
    page: PageContents,
    max_results: int = 50,
    context_lines: int = 8,
    wrap_width: int = 80,
) -> PageContents:
    """Find text pattern(s) in page. Returns a results page with per-match line refs.

    ``pattern`` may be a single string or a list of strings (OR semantics:
    a line is a match if any pattern is a substring, case-insensitive).
    """
    if isinstance(pattern, str):
        patterns = [pattern]
    elif isinstance(pattern, (list, tuple)):
        patterns = [p for p in pattern if isinstance(p, str) and p.strip()]
        if not patterns:
            patterns = [""]
    else:
        patterns = [str(pattern)]
    pats_lower = [p.lower() for p in patterns]

    lines = _wrap_lines(page.text, width=wrap_width, links=None if page.source_url else page.urls)
    anchor_re = re.compile(r"【\d+†[^】]+】")
    search_lines = [anchor_re.sub(_extract_link_text, ln) for ln in lines]

    result_chunks: list[str] = []
    snippets: dict[str, Extract] = {}
    match_idx = 0
    used_lines: set[int] = set()
    hits_per_pat: dict[str, int] = {p: 0 for p in patterns}

    for line_idx in range(len(search_lines)):
        line_lc = search_lines[line_idx].lower()
        matched = [p for p, pl in zip(patterns, pats_lower) if pl and pl in line_lc]
        if not matched:
            continue
        for p in matched:
            hits_per_pat[p] += 1
        if line_idx in used_lines:
            continue

        start = max(0, line_idx - context_lines)
        end = min(len(search_lines), line_idx + context_lines + 1)
        snippet_lines = [
            f"{'>' if i == line_idx else ' '} L{i}: {search_lines[i]}"
            for i in range(start, end)
        ]
        snippet_text = "\n".join(snippet_lines)
        match_tag = f" [matched: {', '.join(repr(m) for m in matched)}]" if len(patterns) > 1 else ""
        # Spell out the next call so the LLM doesn't have to infer the
        # navigation contract from the L<n> notation. open(<match_id>)
        # auto-jumps to source line line_idx via the snippet table below.
        result_chunks.append(
            f"# Match {match_idx} — call open({match_idx}) to jump here "
            f"(source line L{line_idx}){match_tag}\n{snippet_text}"
        )
        snippets[str(match_idx)] = Extract(
            url=page.url,
            text=snippet_text,
            title=f"#{match_idx}",
            line_idx=line_idx,
        )
        used_lines.update(range(start, end))

        if len(result_chunks) >= max_results:
            break
        match_idx += 1

    if result_chunks:
        display_text = "\n\n".join(result_chunks)
        if len(patterns) > 1:
            tally = ", ".join(f"`{p}`={hits_per_pat[p]}" for p in patterns)
            display_text = f"Pattern hits: {tally}\n\n" + display_text
    else:
        missed = [p for p in patterns if hits_per_pat.get(p, 0) == 0]
        hint = _fuzzy_hint(missed, search_lines)
        header = f"No results for pattern(s): {', '.join(repr(p) for p in patterns)}"
        display_text = header + ("\n\n" + hint if hint else "")

    pat_key = "+".join(patterns) if len(patterns) > 1 else patterns[0]
    return PageContents(
        url=f"{page.url}/find?pattern={pat_key}",
        source_url=page.source_url or page.url,
        title=f"Find: `{pat_key}` in `{page.title}`",
        text=display_text,
        urls={str(i): page.url for i in range(len(result_chunks))},
        snippets=snippets,
        metadata=dict(page.metadata),
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def format_skill_result(result: Any, width: int = 80) -> str:
    """按行宽装填 JSON token；只添加空白，不改变字段、层级或顺序。"""
    if width < 1:
        raise ValueError("width must be positive")
    # 字符串（包括转义引号）不可拆分；其余 token 可在边界处换行。
    tokens = re.finditer(r'"(?:[^"\\]|\\.)*"|[{}\[\],:]|[^{}\[\],:\s]+', _json(result))
    lines: list[str] = []
    line = ""
    depth = 0
    previous = ""
    for match in tokens:
        token = match.group()
        closing = token in ("}", "]")
        next_depth = max(0, depth - 1) if closing else depth
        separator = " " if previous in (",", ":") else ""
        if line and len(line) + len(separator) + len(token) > width:
            lines.append(line)
            # 深层结果仍给内容留空间；括号保留准确的原始层级。
            line = " " * min(next_depth * 2, 8, width // 4) + token
        else:
            line += separator + token
        depth = next_depth + (token in ("{", "["))
        previous = token
    if line:
        lines.append(line)
    return "\n".join(lines)
