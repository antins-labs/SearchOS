#!/usr/bin/env python3
"""Reddit RSS feed reader - fetches subreddit posts via official RSS feeds."""

import argparse
import json
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any
from html import unescape
from urllib.parse import urlsplit


def parse_rss_entry(entry: ET.Element) -> dict[str, Any]:
    """Parse an Atom entry from Reddit RSS feed."""
    ns = {'atom': 'http://www.w3.org/2005/Atom', 'media': 'http://search.yahoo.com/mrss/'}
    
    title_elem = entry.find('atom:title', ns)
    title = unescape(title_elem.text) if title_elem is not None and title_elem.text else None
    
    link_elem = entry.find('atom:link', ns)
    link = link_elem.get('href') if link_elem is not None else None
    
    author_elem = entry.find('atom:author/atom:name', ns)
    author = author_elem.text if author_elem is not None and author_elem.text else None
    
    published_elem = entry.find('atom:published', ns)
    published = published_elem.text if published_elem is not None and published_elem.text else None
    
    updated_elem = entry.find('atom:updated', ns)
    updated = updated_elem.text if updated_elem is not None and updated_elem.text else None
    
    content_elem = entry.find('atom:content', ns)
    content = unescape(content_elem.text) if content_elem is not None and content_elem.text else None
    
    summary_elem = entry.find('atom:summary', ns)
    summary = unescape(summary_elem.text) if summary_elem is not None and summary_elem.text else None
    
    category_elem = entry.find('atom:category', ns)
    subreddit = category_elem.get('label') if category_elem is not None else None
    
    # Extract post ID from URL
    post_id = None
    if link and '/comments/' in link:
        parts = link.split('/comments/')
        if len(parts) > 1:
            post_id = parts[1].split('/')[0]
    
    return {
        'id': post_id,
        'title': title,
        'author': author,
        'subreddit': subreddit,
        'url': link,
        'published': published,
        'updated': updated,
        'content': content,
        'summary': summary,
    }


def validate_subreddit_name(name: str) -> str:
    """Validate and normalize subreddit name.
    
    - Removes 'r/' or '/r/' prefix if present
    - Validates name matches Reddit's rules: 2-21 alphanumeric chars and underscores
    - Rejects any path traversal or special characters
    """
    import re
    name = name.strip()
    # Remove r/ or /r/ prefix (case insensitive)
    if name.lower().startswith('r/'):
        name = name[2:]
    elif name.lower().startswith('/r/'):
        name = name[3:]
    # Validate: 2-21 chars, alphanumeric and underscore only
    if not re.match(r'^[A-Za-z0-9_]{2,21}$', name):
        raise ValueError(f"Invalid subreddit name '{name}': must be 2-21 alphanumeric characters or underscores")
    return name


def fetch_subreddit_rss(subreddit: str, limit: int = 25) -> dict[str, Any]:
    """Fetch posts from a subreddit via RSS feed."""
    # Validate limit
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        raise ValueError(f"limit must be an integer between 1 and 100, got {limit}")
    
    # Validate and normalize subreddit name
    subreddit = validate_subreddit_name(subreddit)
    url = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
    
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; RedditRSSReader/1.0)'}
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            if response.status != 200:
                return {
                    'success': False,
                    'error': f'HTTP {response.status}',
                    'url': url,
                    'records': [],
                }
            
            data = response.read().decode('utf-8')
            
            # Validate XML root is an Atom feed
            try:
                root = ET.fromstring(data)
            except ET.ParseError as e:
                return {
                    'success': False,
                    'error': f'Invalid XML: {e}',
                    'url': url,
                    'records': [],
                }
            
            # Check for Atom feed root (must be the official Atom namespace)
            if root.tag != '{http://www.w3.org/2005/Atom}feed':
                # Check if it's an error page or login redirect
                if 'login' in data[:1000].lower() or 'error' in data[:1000].lower():
                    return {
                        'success': False,
                        'error': 'Received non-feed response (possible login page or error)',
                        'url': url,
                        'records': [],
                    }
                return {
                    'success': False,
                    'error': f'Not an Atom feed: root element is {root.tag}',
                    'url': url,
                    'records': [],
                }
            
            entries = root.findall('{http://www.w3.org/2005/Atom}entry')
            posts = []
            
            for entry in entries[:limit]:
                post = parse_rss_entry(entry)
                # Only include posts with valid Reddit comment URLs
                if post.get('url') and '/comments/' in post.get('url', ''):
                    # Validate URL host is reddit.com/www.reddit.com/old.reddit.com
                    try:
                        parsed = urlsplit(post['url'])
                        if parsed.netloc in ('reddit.com', 'www.reddit.com', 'old.reddit.com') and '/comments/' in parsed.path:
                            post['source_url'] = post['url']
                            posts.append(post)
                    except Exception:
                        pass  # Skip invalid URLs
            
            return {
                'success': True,
                'subreddit': subreddit,
                'count': len(posts),
                'source': 'reddit_rss',
                'source_url': url,
                'records': posts,
                'pagination': {
                    'complete': False,
                    'note': 'RSS feed provides limited results; sorting determined by Reddit; may encounter 429 rate limits',
                },
            }
            
    except urllib.error.HTTPError as e:
        return {
            'success': False,
            'error': f'HTTP {e.code}: {e.reason}',
            'url': url,
            'records': [],
        }
    except urllib.error.URLError as e:
        return {
            'success': False,
            'error': f'Network error: {e.reason}',
            'url': url,
            'records': [],
        }
    except ET.ParseError as e:
        return {
            'success': False,
            'error': f'XML parse error: {e}',
            'url': url,
            'records': [],
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'{type(e).__name__}: {e}',
            'url': url,
            'records': [],
        }


def main():
    parser = argparse.ArgumentParser(description='Fetch Reddit subreddit posts via RSS')
    parser.add_argument('--subreddit', '-s', required=True, help='Subreddit name (with or without r/)')
    parser.add_argument('--limit', '-l', type=int, default=25, help='Number of posts to fetch (1-100, default: 25)')
    parser.add_argument('--output', '-o', help='Output JSON file path (default: stdout)')
    
    args = parser.parse_args()
    
    # Validate limit before network request
    if args.limit < 1 or args.limit > 100:
        print(f"Error: --limit must be between 1 and 100, got {args.limit}", file=sys.stderr)
        return 1
    
    try:
        result = fetch_subreddit_rss(args.subreddit, args.limit)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_json + '\n')
    else:
        print(output_json)
    
    if not result.get('success'):
        print(f"Error: {result.get('error')}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())