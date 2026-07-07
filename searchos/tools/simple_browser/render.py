"""HTML → line-numbered markdown rendering (paper §4.2 Simple Browser).

Pure functions: raw HTML in, ``PageContents`` out. No browser state, no
network, no workspace — so both the browser ``tools``/``state`` and the
fetch ``backend`` can import this without a cycle.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import html2text
import lxml.etree
import lxml.html


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


def _replace_images(root: lxml.html.HtmlElement) -> None:
    cnt = 0
    for img_tag in root.findall(".//img"):
        image_name = img_tag.get("alt", img_tag.get("title"))
        replacement = f"[Image {cnt}: {image_name}]" if image_name else f"[Image {cnt}]"
        _replace_node_with_text(img_tag, replacement)
        cnt += 1


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

    urls = _clean_links(root, url)
    _replace_images(root)
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

def _wrap_lines(text: str, width: int = 80) -> list[str]:
    lines = text.split("\n")
    wrapped: list[str] = []
    for line in lines:
        if line:
            wrapped.extend(
                textwrap.wrap(line, width=width, replace_whitespace=False, drop_whitespace=False)
            )
        else:
            wrapped.append("")
    return wrapped


def _truncate(text: str, max_len: int = 100, suffix: str = "...") -> str:
    if len(text) > max_len:
        return text[:max_len - len(suffix)] + suffix
    return text


def _extract_link_text(match: re.Match) -> str:
    """Extract display text from a 【id†text†domain】 anchor."""
    content = match.group(0)
    inner = content[1:-1]
    parts = inner.split("†")
    return parts[1] if len(parts) >= 2 else inner
