"""
HTML processing module - converts HTML to model-readable plain text.
Adapted from GPT-OSS simple_browser/page_contents.py.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import html2text
import lxml.etree
import lxml.html

from ..models import PageContents

logger = logging.getLogger(__name__)

# Regex patterns from GPT-OSS
HTML_SUP_RE = re.compile(r"<sup( [^>]*)?>([\w\-]+)</sup>")
HTML_SUB_RE = re.compile(r"<sub( [^>]*)?>([\w\-]+)</sub>")
HTML_TAGS_SEQ_RE = re.compile(r"(?<=\w)((<[^>]*>)+)(?=\w)")
WHITESPACE_ANCHOR_RE = re.compile(r"(\u3010\@[^\u3011]+\u3011)(\s+)")
EMPTY_LINE_RE = re.compile(r"^\s+$", flags=re.MULTILINE)
EXTRA_NEWLINE_RE = re.compile(r"\n(\s*\n)+")

# Unicode characters that need replacement to avoid conflicts with citation format
_SPECIAL_CHAR_REPLACEMENTS = {
    "\u3010": "\u3016",  # 【 → 〖
    "\u3011": "\u3017",  # 】 → 〗
    "\u25fc": "\u25fe",  # ◼ → ◾
    "\u200b": "",        # zero width space
}


def get_domain(url: str) -> str:
    """Extract domain from a URL."""
    if "http" not in url:
        url = "http://" + url
    return urlparse(url).netloc


def _replace_special_chars(text: str) -> str:
    """Replace special characters that conflict with the citation format."""
    regex = re.compile("(%s)" % "|".join(map(re.escape, _SPECIAL_CHAR_REPLACEMENTS.keys())))
    return regex.sub(lambda mo: _SPECIAL_CHAR_REPLACEMENTS[mo.group(1)], text)


def _merge_whitespace(text: str) -> str:
    """Replace newlines with spaces and merge consecutive whitespace."""
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text)


def _get_text(node: lxml.html.HtmlElement) -> str:
    """Extract all text from an HTML element."""
    return _merge_whitespace(" ".join(node.itertext()))


def _remove_node(node: lxml.html.HtmlElement) -> None:
    """Remove a node from its parent."""
    node.getparent().remove(node)


def _replace_node_with_text(node: lxml.html.HtmlElement, text: str) -> None:
    """Replace an lxml node with a text string while preserving surrounding text."""
    previous = node.getprevious()
    parent = node.getparent()
    tail = node.tail or ""
    if previous is None:
        parent.text = (parent.text or "") + text + tail
    else:
        previous.tail = (previous.tail or "") + text + tail
    parent.remove(node)


def _clean_links(root: lxml.html.HtmlElement, cur_url: str) -> dict[str, str]:
    """Process all anchor tags: replace with 【id†text†domain】 format, return id→url mapping."""
    cur_domain = get_domain(cur_url) if cur_url else ""
    urls: dict[str, str] = {}
    urls_rev: dict[str, str] = {}

    for a in root.findall(".//a[@href]"):
        if a.getparent() is None:
            continue
        link = a.attrib["href"]
        if link.startswith(("mailto:", "javascript:")):
            continue

        text = _get_text(a).replace("\u2020", "\u2021")  # † → ‡
        if not re.sub(r"\u3010\@([^\u3011]+)\u3011", "", text):
            continue
        if link.startswith("#"):
            _replace_node_with_text(a, text)
            continue

        try:
            link = urljoin(cur_url, link)
            domain = get_domain(link)
        except Exception:
            domain = ""
        if not domain:
            continue

        if (link_id := urls_rev.get(link)) is None:
            link_id = f"{len(urls)}"
            urls[link_id] = link
            urls_rev[link] = link_id

        if domain == cur_domain:
            replacement = f"\u3010{link_id}\u2020{text}\u3011"
        else:
            replacement = f"\u3010{link_id}\u2020{text}\u2020{domain}\u3011"
        _replace_node_with_text(a, replacement)

    return urls


def _replace_images(root: lxml.html.HtmlElement) -> None:
    """Replace image tags with numbered placeholders."""
    cnt = 0
    for img_tag in root.findall(".//img"):
        image_name = img_tag.get("alt", img_tag.get("title"))
        if image_name:
            replacement = f"[Image {cnt}: {image_name}]"
        else:
            replacement = f"[Image {cnt}]"
        _replace_node_with_text(img_tag, replacement)
        cnt += 1


def _remove_math(root: lxml.html.HtmlElement) -> None:
    """Remove all <math> elements."""
    for node in root.findall(".//math"):
        _remove_node(node)


def _remove_non_content(root: lxml.html.HtmlElement) -> None:
    # Wikipedia TemplateStyles injects <style> blocks inline with content;
    # html2text keeps their textContent, leaking CSS like ".mw-parser-output ..."
    # into the cleaned markdown.
    for tag in ("style", "script", "noscript", "template"):
        for node in root.findall(f".//{tag}"):
            if node.getparent() is not None:
                _remove_node(node)


def _remove_unicode_smp(text: str) -> str:
    """Remove Unicode characters in the Supplemental Multilingual Plane."""
    smp_pattern = re.compile(r"[\U00010000-\U0001FFFF]", re.UNICODE)
    return smp_pattern.sub("", text)


def _html_to_text(html: str) -> str:
    """Convert HTML string to clean plaintext using html2text."""
    html = re.sub(HTML_SUP_RE, r"^{\2}", html)
    html = re.sub(HTML_SUB_RE, r"_{\2}", html)
    html = re.sub(HTML_TAGS_SEQ_RE, r" \1", html)

    # Monkey-patch escape_md to avoid escaping our link format
    orig_escape_md = html2text.utils.escape_md
    orig_escape_md_section = html2text.utils.escape_md_section
    html2text.utils.escape_md = lambda text, snob=False: text
    html2text.utils.escape_md_section = lambda text, snob=False: text

    h = html2text.HTML2Text()
    h.ignore_links = True
    h.ignore_images = True
    h.body_width = 0
    h.ignore_tables = True
    h.unicode_snob = True
    h.ignore_emphasis = True
    result = h.handle(html).strip()

    html2text.utils.escape_md = orig_escape_md
    html2text.utils.escape_md_section = orig_escape_md_section
    return result


def process_html(
    html: str,
    url: str,
    title: str | None = None,
    display_url: bool = True,
) -> PageContents:
    """Convert HTML into model-readable PageContents.

    This is the main entry point - takes raw HTML and produces structured
    plain text with numbered links, matching the GPT-OSS browser format.
    """
    html = _remove_unicode_smp(html)
    html = _replace_special_chars(html)
    root = lxml.html.fromstring(html)

    # Parse title
    title_element = root.find(".//title")
    if title:
        final_title = title
    elif title_element is not None:
        final_title = title_element.text or ""
    elif url and (domain := get_domain(url)):
        final_title = domain
    else:
        final_title = ""

    # Process links, images, math
    _remove_non_content(root)
    urls = _clean_links(root, url)
    _replace_images(root)
    _remove_math(root)

    # Convert to text
    clean_html = lxml.etree.tostring(root, encoding="UTF-8").decode()
    text = _html_to_text(clean_html)

    # Clean up whitespace around anchors
    text = re.sub(WHITESPACE_ANCHOR_RE, lambda m: m.group(2) + m.group(1), text)
    text = re.sub(EMPTY_LINE_RE, "", text)
    text = re.sub(EXTRA_NEWLINE_RE, "\n\n", text)

    # Prepend URL if requested
    top_parts = []
    if display_url and url:
        top_parts.append(f"\nURL: {url}\n")

    return PageContents(
        url=url,
        text="".join(top_parts) + text,
        urls=urls,
        title=final_title,
    )
