#!/usr/bin/env python3
"""
获取 X/Twitter 用户公开资料
从用户主页 HTML HEAD 部分提取元数据
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

# 严格超时控制：单次请求10秒，最多2次重试，总上限约40秒
REQUEST_TIMEOUT = 10
MAX_RETRIES = 2
RETRY_DELAY = 1
MAX_HEAD_SIZE = 128 * 1024  # 最多读取 128KB


class MetaTagParser(HTMLParser):
    """解析 HTML HEAD 中的 meta 标签，正确处理属性顺序和 HTML 实体。"""
    
    def __init__(self):
        super().__init__()
        self.meta_tags: dict[str, str] = {}
        self.in_head = True
        self.head_ended = False
    
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == 'head':
            self.in_head = True
            return
        
        if tag.lower() == '/head':
            self.head_ended = True
            return
        
        if tag.lower() != 'meta':
            return
        
        # 收集属性
        attrs_dict: dict[str, str] = {}
        for name, value in attrs:
            if value is not None:
                attrs_dict[name.lower()] = value
        
        # 查找 property 或 name 属性
        prop_name = attrs_dict.get('property') or attrs_dict.get('name')
        content = attrs_dict.get('content', '')
        
        if prop_name and content:
            # 存储 meta 标签内容
            self.meta_tags[prop_name] = content
    
    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == 'head':
            self.head_ended = True


def parse_head_meta(html_head: str) -> dict[str, str]:
    """解析 HTML HEAD 部分的 meta 标签。"""
    parser = MetaTagParser()
    try:
        parser.feed(html_head)
    except Exception:
        pass
    return parser.meta_tags


def validate_username(username: str) -> None:
    """验证用户名格式。"""
    username = username.lstrip('@')
    if not username:
        raise ValueError('用户名不能为空')
    if len(username) > 15:
        raise ValueError(f'用户名过长: {len(username)} 字符（最大 15）')
    if not re.match(r'^[A-Za-z0-9_]+$', username):
        raise ValueError(f'用户名包含无效字符: {username}')


def fetch_head_only(url: str) -> tuple[int, str]:
    """
    仅获取 HTML HEAD 部分。
    分块读取，遇到 </head> 立即停止。
    最多读取 MAX_HEAD_SIZE 字节。
    """
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Cache-Control': 'no-cache',
    })
    
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            # 使用 urlopen 但分块读取
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                status = resp.status if hasattr(resp, 'status') else 200
                
                # 分块读取直到找到 </head>
                chunks: list[bytes] = []
                total_read = 0
                head_found = False
                
                while total_read < MAX_HEAD_SIZE:
                    try:
                        chunk = resp.read1(4096)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        total_read += len(chunk)
                        
                        # 检查是否已包含 </head>
                        combined = b''.join(chunks)
                        if b'</head>' in combined.lower():
                            head_found = True
                            break
                    except Exception:
                        break
                
                # 关闭响应（停止下载剩余内容）
                if hasattr(resp, 'close'):
                    resp.close()
                
                html_bytes = b''.join(chunks)
                html_text = html_bytes.decode('utf-8', errors='replace')
                
                # 截取到 </head>
                head_end = html_text.lower().find('</head>')
                if head_end != -1:
                    html_text = html_text[:head_end + 7]
                
                return status, html_text
                
        except urllib.error.HTTPError as e:
            return e.code, ''
        except TimeoutError:
            last_error = f'请求超时 ({REQUEST_TIMEOUT}s)'
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
        except urllib.error.URLError as e:
            last_error = f'网络错误: {e.reason}'
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
        except Exception as e:
            last_error = str(e)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
    
    raise RuntimeError(last_error or '请求失败')


def extract_user_meta(meta_tags: dict[str, str]) -> dict:
    """从 meta 标签字典提取用户资料。"""
    result: dict = {}
    
    # og:title 格式: "Display Name (@username) on X"
    og_title = meta_tags.get('og:title', '')
    if og_title:
        result['og_title'] = og_title
        match = re.match(r'^(.+?)\s*\(@([^)]+)\)', og_title)
        if match:
            result['display_name'] = match.group(1).strip()
            result['username'] = match.group(2)
    
    # og:description - 个人简介
    og_desc = meta_tags.get('og:description', '')
    if og_desc:
        result['description'] = og_desc
    
    # og:image - 头像
    og_image = meta_tags.get('og:image', '')
    if og_image:
        result['profile_image_url'] = og_image
    
    # og:url - 用户主页
    og_url = meta_tags.get('og:url', '')
    if og_url:
        result['url'] = og_url
    
    # twitter:label1 + twitter:data1 - 通常是发帖数
    label1 = meta_tags.get('twitter:label1', '')
    data1 = meta_tags.get('twitter:data1', '')
    if label1 and data1:
        label_key = label1.lower().replace(' ', '_')
        result[label_key] = data1
    
    # twitter:label2 + twitter:data2 - 通常是加入时间
    label2 = meta_tags.get('twitter:label2', '')
    data2 = meta_tags.get('twitter:data2', '')
    if label2 and data2:
        label_key = label2.lower().replace(' ', '_')
        result[label_key] = data2
    
    return result


def get_user(username: str) -> dict | None:
    """获取用户资料信息。"""
    username = username.lstrip('@')
    validate_username(username)
    
    url = f"https://x.com/{username}"
    
    try:
        status, html_head = fetch_head_only(url)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f'请求失败: {e}')
    
    if status == 404:
        return None
    
    if status != 200:
        raise RuntimeError(f'HTTP {status}')
    
    # 检查是否有有效的 HEAD 内容
    if not html_head or len(html_head) < 100:
        raise RuntimeError('页面内容过短或缺少 HEAD 部分')
    
    # 解析 meta 标签
    meta_tags = parse_head_meta(html_head)
    
    if not meta_tags:
        raise RuntimeError('未找到任何 meta 标签')
    
    # 提取用户资料
    user_data = extract_user_meta(meta_tags)
    
    # 验证用户名
    extracted_username = user_data.get('username', '')
    if not extracted_username:
        raise RuntimeError('无法从页面提取用户名')
    
    if extracted_username.lower() != username.lower():
        print(f"警告: 用户名不匹配: 请求={username}, 返回={extracted_username}", file=sys.stderr)
        return None
    
    return {
        'username': extracted_username,
        'display_name': user_data.get('display_name', ''),
        'description': user_data.get('description', ''),
        'profile_image_url': user_data.get('profile_image_url', ''),
        'posts_count': user_data.get('posts', ''),
        'joined': user_data.get('joined', ''),
        'url': user_data.get('url', url),
        'source_url': url
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='获取 X/Twitter 用户公开资料',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  %(prog)s --username NASA
  %(prog)s --username jack --output user.json
'''
    )
    parser.add_argument('--username', '-u', required=True, help='用户名（不含 @）')
    parser.add_argument('--output', '-o', default='', help='输出 JSON 文件路径（默认输出到 stdout）')
    
    args = parser.parse_args()
    
    try:
        user = get_user(args.username)
        
        result = {
            'records': [user] if user else [],
            'query': {'username': args.username}
        }
        
        output_json = json.dumps(result, ensure_ascii=False, indent=2)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output_json)
        else:
            print(output_json)
        
        if not user:
            print(f"错误: 用户不存在或资料不可用: {args.username}", file=sys.stderr)
            return 1
        
        return 0
        
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())