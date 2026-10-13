#!/usr/bin/env python3
"""检索 arXiv 或解析离线 Atom；仅依赖 Python 标准库。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

DEFAULT_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_DELAY = 5.0


def parse_records(content: bytes) -> list[dict]:
    root = ET.fromstring(content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    records = []
    for entry in root.findall("a:entry", ns):
        source = entry.findtext("a:id", default="", namespaces=ns).strip()
        if "api/errors" in source:
            raise ValueError(entry.findtext("a:summary", default="arXiv API error", namespaces=ns))
        records.append({
            "source_url": source,
            "title": " ".join(entry.findtext("a:title", default="", namespaces=ns).split()),
            "authors": [a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns)],
            "summary": " ".join(entry.findtext("a:summary", default="", namespaces=ns).split()),
            "published": entry.findtext("a:published", default="", namespaces=ns),
        })
    return records


def fetch_with_retry(url: str, timeout: float, max_retries: int, retry_delay: float) -> bytes:
    """带重试的 HTTP GET，处理超时与临时网络错误。"""
    request = Request(url, headers={"User-Agent": "portable-arxiv-search/1.0"})
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read(10_000_001)
        except HTTPError as exc:
            if exc.code == 400:
                # Bad Request: usually invalid query syntax
                raise RuntimeError(f"arXiv API 返回 400 Bad Request，请检查查询语法: {url}") from exc
            if exc.code == 429:
                # Too Many Requests: wait and retry
                last_error = exc
                if attempt < max_retries:
                    import time
                    time.sleep(retry_delay * attempt)
                    continue
                raise RuntimeError(f"arXiv API 限流，已重试 {max_retries} 次") from exc
            if 500 <= exc.code < 600 and attempt < max_retries:
                last_error = exc
                import time
                time.sleep(retry_delay * attempt)
                continue
            raise RuntimeError(f"arXiv API HTTP {exc.code}: {exc.reason}") from exc
        except (URLError, socket.timeout, TimeoutError) as exc:
            last_error = exc
            if attempt < max_retries:
                import time
                time.sleep(retry_delay * attempt)
                continue
            raise RuntimeError(f"arXiv API 连接超时或网络错误，已重试 {max_retries} 次: {exc}") from exc
    raise RuntimeError(f"arXiv API 请求失败: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检索 arXiv 或解析离线 Atom；仅依赖 Python 标准库。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
参数说明:
  --query QUERY    arXiv 查询表达式，例如 'all:\"retrieval augmented generation\"' 或 'au:Bengio'
  --limit N        返回记录数上限，范围 1-100，默认 5
  --timeout SEC    HTTP 超时秒数，默认 60
  --input FILE     离线 Atom XML 文件路径，用于无网络环境验证解析逻辑
  --output FILE    JSON 输出文件路径；未指定时输出到标准输出

示例:
  # 在线检索
  python scripts/search.py --query 'all:\"large language models\"' --limit 10

  # 离线解析
  python scripts/search.py --input references/example.atom --output sample.json
"""
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--query", help="arXiv 查询表达式")
    source.add_argument("--input", type=Path, help="离线 Atom XML，仅用于验证")
    parser.add_argument("--limit", type=int, default=5, help="返回记录数上限 (1-100)，默认 5")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"HTTP 超时秒数，默认 {DEFAULT_TIMEOUT}")
    parser.add_argument("--output", type=Path, help="JSON 输出文件路径")
    args = parser.parse_args()

    if not 1 <= args.limit <= 100:
        parser.error("--limit 必须在 1 至 100 之间")

    try:
        request_url = None
        if args.input:
            content = args.input.read_bytes()
        else:
            request_url = "https://export.arxiv.org/api/query?" + urlencode({
                "search_query": args.query,
                "start": 0,
                "max_results": args.limit,
            })
            content = fetch_with_retry(request_url, args.timeout, MAX_RETRIES, RETRY_DELAY)

        if len(content) > 10_000_000:
            raise ValueError("Atom 响应超过 10 MB 限制")

        data = {
            "input_mode": "fixture" if args.input else "live",
            "request_url": request_url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "records": parse_records(content)[:args.limit],
        }
        if request_url:
            data["sources"] = [{"url": request_url, "content": content.decode("utf-8")}]

        rendered = json.dumps(data, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(json.dumps({"records": len(data["records"]), "output": str(args.output)}))
        else:
            print(rendered)
        return 0
    except Exception as exc:
        print(f"arxiv-search: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
