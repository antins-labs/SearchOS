#!/usr/bin/env python3
"""
获取 X/Twitter 公开帖子详情
通过官方 publish.twitter.com/oembed 接口获取公开帖子信息
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
    """从 HTML 中提取纯文本，保留换行。"""
    
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
    """从 oEmbed HTML 中提取纯文本。"""
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
    """从帖子 URL 提取用户名。"""
    match = re.search(r'(?:x\.com|twitter\.com)/([^/]+)/status/', url)
    if match:
        return match.group(1)
    return ''


def validate_tweet_id(tweet_id: str) -> None:
    """验证帖子 ID 为正整数。"""
    if not tweet_id:
        raise ValueError('帖子 ID 不能为空')
    if not tweet_id.isdigit():
        raise ValueError(f'无效的帖子 ID: {tweet_id}（必须为数字）')
    if int(tweet_id) <= 0:
        raise ValueError(f'无效的帖子 ID: {tweet_id}（必须为正整数）')


def validate_tweet_url(url: str) -> tuple[str, str] | None:
    """验证并解析帖子 URL。"""
    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception:
        return None
    
    host = parsed.netloc.lower()
    if host not in ('x.com', 'twitter.com', 'www.x.com', 'www.twitter.com'):
        return None
    
    match = re.match(r'^/([^/]+)/status/(\d+)$', parsed.path)
    if not match:
        return None
    
    return match.group(2), match.group(1)


def fetch_oembed(tweet_id: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """通过 oEmbed API 获取帖子数据，带重试。"""
    validate_tweet_id(tweet_id)
    
    api_url = (
        f"https://publish.twitter.com/oembed"
        f"?url=https%3A%2F%2Ftwitter.com%2Fplaceholder%2Fstatus%2F{tweet_id}"
        f"&omit_script=true"
    )
    
    req = urllib.request.Request(api_url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; bot)',
        'Accept': 'application/json',
    })
    
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    raise ValueError(f'意外的 HTTP 状态: {resp.status}')
                data = resp.read()
                return json.loads(data.decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in (404, 403):
                raise
            last_error = f'HTTP {e.code}: {e.reason}'
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
        except TimeoutError:
            last_error = f'请求超时 ({timeout}s)'
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
        except urllib.error.URLError as e:
            last_error = f'网络错误: {e.reason}'
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
        except json.JSONDecodeError as e:
            raise ValueError(f'响应 JSON 解析失败: {e}') from e
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
    
    raise RuntimeError(last_error or '请求失败')


def get_tweet(tweet_id: str, expected_username: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict | None:
    """根据 ID 获取帖子详情。"""
    try:
        data = fetch_oembed(tweet_id, timeout)
    except urllib.error.HTTPError as e:
        if e.code in (404, 403):
            return None
        raise
    except TimeoutError:
        raise RuntimeError(f'请求超时 ({timeout}s)')
    
    url = data.get('url', '')
    author_name = data.get('author_name', '')
    raw_html = data.get('html', '')
    
    text = extract_text_from_html(raw_html)
    username = extract_username_from_url(url)
    
    if not url.endswith(f'/{tweet_id}'):
        print(f"警告: 返回的帖子 ID 不匹配: URL={url}, 期望 ID={tweet_id}", file=sys.stderr)
        return None
    
    if expected_username and username.lower() != expected_username.lower():
        print(f"警告: 用户名不匹配: 返回={username}, 期望={expected_username}", file=sys.stderr)
        return None
    
    return {
        'id': tweet_id,
        'author_name': author_name,
        'author_username': username,
        'text': text,
        'url': url,
        'source_url': f"https://publish.twitter.com/oembed?url=https://twitter.com/placeholder/status/{tweet_id}"
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='获取 X/Twitter 公开帖子详情',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  %(prog)s --id 20
  %(prog)s --url "https://x.com/jack/status/20"
  %(prog)s --id 20 --username jack
  %(prog)s --id 20 --output tweet.json
'''
    )
    parser.add_argument('--id', '-i', help='帖子 ID')
    parser.add_argument('--url', '-u', help='帖子 URL (支持 twitter.com 和 x.com)')
    parser.add_argument('--username', help='预期用户名（用于验证，可选）')
    parser.add_argument('--output', '-o', default='', help='输出 JSON 文件路径（默认输出到 stdout）')
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT, help='请求超时秒数')
    
    args = parser.parse_args()
    
    if not args.id and not args.url:
        parser.error('必须提供 --id 或 --url')
    
    tweet_id = args.id
    expected_username = args.username
    
    if args.url:
        parsed = validate_tweet_url(args.url)
        if not parsed:
            print("错误: 无效的帖子 URL（必须为 x.com 或 twitter.com 的 status 链接）", file=sys.stderr)
            return 1
        tweet_id = parsed[0]
        if not expected_username:
            expected_username = parsed[1]
    
    if not tweet_id:
        print("错误: 无法解析帖子 ID", file=sys.stderr)
        return 1
    
    try:
        tweet = get_tweet(tweet_id, expected_username, args.timeout)
        
        result = {
            'records': [tweet] if tweet else [],
            'query': {'tweet_id': tweet_id, 'expected_username': expected_username}
        }
        
        output_json = json.dumps(result, ensure_ascii=False, indent=2)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_json)
        else:
            print(output_json)
        
        if not tweet:
            print(f"错误: 帖子不存在或非公开: {tweet_id}", file=sys.stderr)
            return 1
        
        return 0
        
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"网络错误: {e.reason}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())