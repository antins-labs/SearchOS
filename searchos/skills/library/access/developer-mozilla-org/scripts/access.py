#!/usr/bin/env python3
"""MDN (developer.mozilla.org) access skill CLI.

Reads MDN reference documents and lists reference index entries.
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE = "https://developer.mozilla.org/en-US"
UA = "Mozilla/5.0 (compatible; SearchOS-MDN/1.0; +skill)"
MAX_RETRIES = 3
TIMEOUT = 45

CAPABILITIES = ("read_document", "list_reference_index")


def get_proxy_mode():
    return os.environ.get("SEARCHOS_PROXY_MODE", "inherit")


def make_opener():
    """Return an opener honoring the proxy mode via environment."""
    proxy_mode = get_proxy_mode()
    if proxy_mode == "direct":
        # bypass application proxies
        handler = urllib.request.ProxyHandler({})
        return urllib.request.build_opener(handler)
    return urllib.request.build_opener()  # default honors env proxies


def fetch(url):
    """Fetch a URL with retries; return (final_url, html_text)."""
    opener = make_opener()
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            resp = opener.open(req, timeout=TIMEOUT)
            body = resp.read().decode("utf-8", "replace")
            return resp.url, body
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                last_err = e
                retry = e.headers.get("Retry-After")
                wait = min(float(retry) if retry and float(retry) <= 30 else 2.0, 30.0) if retry else 2.0
                time.sleep(wait)
                continue
            raise  # 404, 4xx auth etc -> propagate
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            time.sleep(2.0)
            continue
    raise urllib.error.URLError(
        f"fetch failed after {MAX_RETRIES} attempts: {last_err}"
    )


def _text(el):
    return el.get_text(" ", strip=True) if el is not None else None


def read_document(inp):
    path = inp.get("path")
    if not isinstance(path, str) or not path.strip():
        return invalid_input("read_document", "field 'path' must be a non-empty string")
    url = BASE + path
    final_url, html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one("h1")
    title = _text(title_el)

    # summary: the descriptive paragraph(s) right after h1 / baseline banner
    summary = None
    main = soup.select_one("main#content") or soup
    if main:
        h1 = main.select_one("h1")
        if h1:
            nxt = h1.find_next_sibling()
            # skip baseline banner div(s)
            guard = 0
            while nxt and guard < 5:
                if nxt.name == "p":
                    summary = _text(nxt)
                    break
                nxt = nxt.find_next_sibling()
                guard += 1
        if summary is None:
            # fallback: first paragraph in the first content section
            sec = main.select_one("section.content-section")
            if sec:
                p = sec.find("p")
                if p:
                    summary = _text(p)

    # full content: all content sections under main
    content_parts = []
    if main:
        for sec in main.select("section.content-section"):
            h = sec.find("h2")
            if h and h.get("id") == "feedback":
                continue
            txt = _text(sec)
            if txt:
                content_parts.append(txt)
    content = "\n\n".join(content_parts)
    if not content and summary:
        content = summary

    # browser_compatibility: prefer the static "Baseline" indicator banner
    # (actual rendered page content), else fall back to the Browser Compat Data
    # query identifier exposed by the (JS-rendered) compatibility table element.
    browser_compatibility = None
    baseline = soup.select_one(".baseline-indicator")
    if baseline is not None:
        text = baseline.get_text(" ", strip=True)
        if text:
            browser_compatibility = text
    else:
        compat_el = soup.select_one("mdn-compat-table-lazy")
        if compat_el is not None and compat_el.has_attr("query"):
            browser_compatibility = compat_el["query"]

    # specifications: links in the Specifications section
    specifications = []
    spec_h2 = soup.find("h2", id="specifications")
    if spec_h2:
        sec = spec_h2.parent if spec_h2.parent else spec_h2
        # the section element containing the h2
        for a in sec.find_all("a", href=True):
            href = a["href"]
            txt = a.get_text(strip=True)
            if href.startswith("http") and not href.startswith(BASE):
                specifications.append({"title": txt, "url": href})

    if not title:
        # possibly a 404 / invalid page with no clear doc
        # final_url present, treat as parsed-empty
        return {"status": "empty", "records": [], "warnings": [
            "no document title parsed at source"
        ]}

    record = {
        "title": title,
        "summary": summary,
        "content": content,
        "source_url": final_url,
        "browser_compatibility": browser_compatibility,
        "specifications": specifications,
    }
    return {"status": "ok", "records": [record], "warnings": []}


def list_reference_index(inp):
    section = inp.get("section")
    if not isinstance(section, str) or not section.strip():
        return invalid_input("list_reference_index", "field 'section' must be a non-empty string")
    url = BASE + section
    final_url, html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    doc_links = []  # (title, absolute_url)
    seen = set()

    idx = soup.select_one("div.index")
    if idx is not None:
        for a in idx.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/en-US/docs/") or href.startswith(BASE + "/docs/"):
                title = a.get_text(" ", strip=True)
                abs_url = urljoin(BASE, href) if not href.startswith("http") else href
                key = (title, abs_url)
                if key not in seen:
                    seen.add(key)
                    doc_links.append(key)

    # also include content-section doc links (covers categorized index pages
    # such as JS Global Objects and CSS Reference sub-groups)
    body = soup.select_one(".layout__body") or soup
    for sec in body.find_all("section", class_="content-section"):
        h2 = sec.find("h2")
        if h2 and h2.get("id") == "feedback":
            continue
        for a in sec.find_all("a", href=True):
            href = a["href"]
            if href.startswith("/en-US/docs/") or href.startswith(BASE + "/docs/"):
                title = a.get_text(" ", strip=True)
                abs_url = urljoin(BASE, href) if not href.startswith("http") else href
                key = (title, abs_url)
                if key not in seen:
                    seen.add(key)
                    doc_links.append(key)

    records = [
        {"title": title, "source_url": url}
        for title, url in doc_links
    ]

    # dedupe by source_url keeping first
    dedup = {}
    for r in records:
        if r["source_url"] not in dedup:
            dedup[r["source_url"]] = r
    records = list(dedup.values())

    if not records:
        return {"status": "empty", "records": [], "warnings": [
            "no reference entries parsed from section source"
        ]}
    return {"status": "ok", "records": records, "warnings": []}


def invalid_input(cap, msg):
    return {"status": "invalid_input", "records": [], "warnings": [f"{cap}: {msg}"]}


HANDLERS = {
    "read_document": read_document,
    "list_reference_index": list_reference_index,
}


def main(argv):
    parser = argparse.ArgumentParser(
        prog="access.py",
        description="Access skill for MDN (developer.mozilla.org).",
    )
    parser.add_argument("capability", nargs="?", choices=list(CAPABILITIES),
                        help="capability id")
    parser.add_argument("--input", help="JSON object input")
    args = parser.parse_args(argv)

    if not args.capability:
        parser.print_help()
        return 0

    if not args.input:
        print(json.dumps(invalid_input(args.capability, "missing --input JSON"), ensure_ascii=False))
        return 2

    try:
        inp = json.loads(args.input)
    except json.JSONDecodeError:
        print(json.dumps({"status": "invalid_input", "records": [],
                           "warnings": ["input is not valid JSON"]}, ensure_ascii=False))
        return 2

    if not isinstance(inp, dict):
        print(json.dumps({"status": "invalid_input", "records": [],
                           "warnings": ["input must be a JSON object"]}, ensure_ascii=False))
        return 2

    handler = HANDLERS[args.capability]
    try:
        result = handler(inp)
    except urllib.error.HTTPError as e:
        result = {"status": "error", "records": [], "warnings": [
            f"http error {e.code} fetching {e.url}"
        ]}
        print(json.dumps(result, ensure_ascii=False))
        return 1
    except urllib.error.URLError as e:
        result = {"status": "error", "records": [], "warnings": [
            f"network error: {e.reason}"
        ]}
        print(json.dumps(result, ensure_ascii=False))
        return 1
    except (TimeoutError, OSError) as e:
        result = {"status": "error", "records": [], "warnings": [
            f"transport error: {e}"
        ]}
        print(json.dumps(result, ensure_ascii=False))
        return 1
    except Exception as e:  # parsing failure
        result = {"status": "error", "records": [], "warnings": [
            f"parser failure: {e}"
        ]}
        print(json.dumps(result, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    if result["status"] == "invalid_input":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
