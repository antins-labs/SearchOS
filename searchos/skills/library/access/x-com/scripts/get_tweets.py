#!/usr/bin/env python3
"""
批量获取 X/Twitter 公开帖子详情
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

DEFAULT_TIMEOUT = 15
MAX_RETRIES = 2
RETRY_DELAY = 1


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
    
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'br':
            self.text_parts.append('\n')
    
    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
    
    def get_text(self) -> str:
        return ''.join(self.text_parts)


def extract_text_from_html(raw_html: str) -> str:
    match = re.search(r'<p[^>]*>(.*?)</p>', raw_html, re.DOTALL)
    if not match:
        return ''
    inner = match.group(1)
    extractor = TextExtractor()
    try:
        extractor.feed(inner)
    except Exception:
        inner = re.sub(r'<[^>]+>', '', inner)
        return html.unescape(inner).strip()
    text = extractor.get_text()
    text = html.unescape(text)
    return text.strip()


def extract_username_from_url(url: str) -> str:
    match = re.search(r'(?:x\.com|twitter\.com)/([^/]+)/status/', url)
    return match.group(1) if match else ''


def validate_tweet_id(tweet_id: str) -> bool:
    return bool(tweet_id and tweet_id.isdigit() and int(tweet_id) > 0)


def validate_tweet_url(url: str) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return None
    host = parsed.netloc.lower()
    if host not in ('x.com', 'twitter.com', 'www.x.com', 'www.twitter.com'):
        return None
    match = re.match(r'^/([^/]+)/status/(\d+)$', parsed.path)
    return match.group(2) if match else None


def fetch_oembed(tweet_id: str, timeout: int = DEFAULT_TIMEOUT) -> dict | None:
    if not validate_tweet_id(tweet_id):
        return None
    
    api_url = f"https://publish.twitter.com/oembed?url=https%3A%2F%2Ftwitter.com%2Fplaceholder%2Fstatus%2F{tweet_id}&omit_script=true"
    req = urllib.request.Request(api_url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; bot)',
        'Accept': 'application/json',
    })
    
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in (404, 403):
                return None
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise RuntimeError(f'HTTP {e.code}: {e.reason}') from e
        except TimeoutError:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise RuntimeError(f'请求超时 ({timeout}s)')
        except json.JSONDecodeError:
            return None
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise RuntimeError(f'网络错误: {e.reason}')
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            raise RuntimeError(str(e))
    return None


def get_tweet(tweet_id: str, timeout: int = DEFAULT_TIMEOUT) -> dict | None:
    data = fetch_oembed(tweet_id, timeout)
    if not data:
        return None
    
    url = data.get('url', '')
    raw_html = data.get('html', '')
    text = extract_text_from_html(raw_html)
    username = extract_username_from_url(url)
    
    if not url.endswith(f'/{tweet_id}'):
        return None
    
    return {
        'id': tweet_id,
        'author_name': data.get('author_name', ''),
        'author_username': username,
        'text': text,
        'url': url,
        'source_url': f"https://publish.twitter.com/oembed?url=https://twitter.com/placeholder/status/{tweet_id}"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='批量获取 X/Twitter 公开帖子详情')
    parser.add_argument('--ids', '-i', help='帖子 ID 列表，逗号分隔')
    parser.add_argument('--file', '-f', help='包含帖子 ID 的文件（每行一个）')
    parser.add_argument('--output', '-o', default='', help='输出 JSON 文件路径')
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT, help='请求超时秒数')
    parser.add_argument('--continue-on-error', action='store_true', help='遇到错误继续处理')
    
    args = parser.parse_args()
    
    tweet_ids: list[str] = []
    invalid_inputs: list[str] = []
    
    if args.ids:
        for id_str in args.ids.split(','):
            id_str = id_str.strip()
            if not id_str:
                continue
            if validate_tweet_id(id_str):
                tweet_ids.append(id_str)
            else:
                parsed = validate_tweet_url(id_str)
                if parsed:
                    tweet_ids.append(parsed)
                else:
                    invalid_inputs.append(id_str)
    
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if validate_tweet_id(line):
                        tweet_ids.append(line)
                    else:
                        parsed = validate_tweet_url(line)
                        if parsed:
                            tweet_ids.append(parsed)
                        else:
                            invalid_inputs.append(line)
        except FileNotFoundError:
            print(f"错误: 文件不存在: {args.file}", file=sys.stderr)
            return 1
        except IOError as e:
            print(f"错误: 无法读取文件 {args.file}: {e}", file=sys.stderr)
            return 1
    
    if invalid_inputs:
        print(f"警告: 跳过无效输入: {', '.join(invalid_inputs)}", file=sys.stderr)
    
    if not tweet_ids:
        parser.error('必须提供有效的帖子 ID（通过 --ids 或 --file）')
    
    seen: set[str] = set()
    unique_ids: list[str] = []
    for tid in tweet_ids:
        if tid not in seen:
            seen.add(tid)
            unique_ids.append(tid)
    tweet_ids = unique_ids
    
    records: list[dict] = []
    errors: list[dict] = []
    
    for tid in tweet_ids:
        try:
            tweet = get_tweet(tid, args.timeout)
            if tweet:
                records.append(tweet)
            else:
                errors.append({'id': tid, 'error': '帖子不存在或非公开'})
        except RuntimeError as e:
            errors.append({'id': tid, 'error': str(e)})
        except Exception as e:
            errors.append({'id': tid, 'error': f'未知错误: {e}'})
    
    result = {
        'records': records,
        'query': {'tweet_ids': tweet_ids, 'total_requested': len(tweet_ids)},
        'summary': {'found': len(records), 'not_found': len(errors)}
    }
    
    if errors:
        result['errors'] = errors
    
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    
    if args.output:
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_json)
        except IOError as e:
            print(f"错误: 无法写入文件 {args.output}: {e}", file=sys.stderr)
            return 1
    else:
        print(output_json)
    
    if errors:
        print(f"警告: {len(errors)}/{len(tweet_ids)} 个帖子获取失败", file=sys.stderr)
        for err in errors:
            print(f"  - {err['id']}: {err['error']}", file=sys.stderr)
        if not args.continue_on_error:
            return 1
    
    if not records:
        print("错误: 所有帖子均获取失败", file=sys.stderr)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())