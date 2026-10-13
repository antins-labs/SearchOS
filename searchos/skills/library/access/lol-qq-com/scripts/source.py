"""
SearchOS Access Skill for lol.qq.com
Fetches article/news content from League of Legends China official site.

Target: https://lol.qq.com/news/detail_m.html?docid=...
API: https://apps.game.qq.com/cmc/zmMcnContentInfo (JSONP)
"""

import asyncio
import aiohttp
import json
import re
from html.parser import HTMLParser
from typing import Any


class HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML content"""
    
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_tags = {'script', 'style', 'noscript'}
        self.current_tag = None
        
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag.lower()
        # Add newlines for block elements
        if tag.lower() in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.text_parts.append('\n')
    
    def handle_endtag(self, tag):
        if tag.lower() in ('p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.text_parts.append('\n')
    
    def handle_data(self, data):
        if self.current_tag not in self.skip_tags:
            text = data.strip()
            if text:
                self.text_parts.append(text)
    
    def get_text(self) -> str:
        return '\n'.join(self.text_parts)


def extract_images(html_content: str) -> list[dict]:
    """Extract image URLs and alt text from HTML"""
    img_pattern = r'<img[^>]+src=["\']([^"\']+)["\'][^>]*(?:alt=["\']([^"\']*)["\'])?[^>]*>'
    images = []
    
    for match in re.finditer(img_pattern, html_content, re.IGNORECASE):
        url = match.group(1)
        alt = match.group(2) or ""
        # Clean up URL (unescape HTML entities)
        url = url.replace('&amp;', '&')
        images.append({
            'url': url,
            'alt': alt.strip()
        })
    
    return images


def html_to_text(html_content: str) -> str:
    """Convert HTML to plain text"""
    parser = HTMLTextExtractor()
    parser.feed(html_content)
    text = parser.get_text()
    # Clean up excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def fetch_article_detail(docid: str) -> dict[str, Any]:
    """
    Fetch article detail by docid from lol.qq.com
    
    Args:
        docid: Article document ID (e.g., "10255542153636928057")

    
    Returns:
        dict with article data or error
    """
    api_url = f"https://apps.game.qq.com/cmc/zmMcnContentInfo"
    params = {
        'r0': 'jsonp',
        'source': 'web_pc',
        'type': '0',
        'docid': docid
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://lol.qq.com/',
        'Accept': '*/*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return {
                        'error': f'HTTP {resp.status}',
                        'error_code': 'HTTP_ERROR'
                    }
                
                text = await resp.text(encoding='utf-8')
                
                # Parse JSONP response: callback({...})
                json_match = re.search(r'callback\((\{.*\})\)', text, re.DOTALL)
                if not json_match:
                    return {
                        'error': 'Failed to parse JSONP response',
                        'error_code': 'PARSE_ERROR'
                    }
                
                data = json.loads(json_match.group(1))
                
                # Check API status
                if data.get('status') != 1:
                    return {
                        'error': data.get('msg', 'API returned error'),
                        'error_code': 'API_ERROR'
                    }
                
                # Extract article data
                if 'data' not in data or 'result' not in data['data']:
                    return {
                        'error': 'No article data in response',
                        'error_code': 'NO_DATA'
                    }
                
                result = data['data']['result']
                
                # Process content
                html_content = result.get('sContent', '')
                plain_text = html_to_text(html_content) if html_content else ""
                images = extract_images(html_content) if html_content else []
                
                # Build article object
                article = {
                    'docid': result.get('iDocID'),
                    'title': result.get('sTitle', ''),
                    'author': result.get('sAuthor', ''),
                    'author_id': result.get('authorID'),
                    'avatar': result.get('avatar', ''),
                    'created_at': result.get('sCreated', ''),
                    'indexed_at': result.get('sIdxTime', ''),
                    'source': result.get('sSource', ''),
                    'source_id': result.get('iSourceId'),
                    'views': result.get('iTotalPlay', 0),
                    'comments': result.get('iComment', 0),
                    'can_comment': result.get('iCanCmt', 0) == 1,
                    'tags': result.get('sTagIds', '').split(',') if result.get('sTagIds') else [],
                    'cover_image': result.get('sIMG', ''),
                    'url': f"https://lol.qq.com/news/detail_m.html?docid={docid}",
                    'content_html': html_content,
                    'content_text': plain_text,
                    'images': images,
                    'uuid': result.get('uuid', ''),
                }
                
                return {
                    'success': True,
                    'article': article
                }
                
    except asyncio.TimeoutError:
        return {
            'error': 'Request timeout',
            'error_code': 'TIMEOUT'
        }
    except json.JSONDecodeError as e:
        return {
            'error': f'JSON parse error: {str(e)}',
            'error_code': 'JSON_ERROR'
        }
    except Exception as e:
        return {
            'error': str(e),
            'error_code': 'UNKNOWN_ERROR'
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for SearchOS skill execution.
    
    Args:
        params: Dict with 'function' key and function-specific parameters

    
    Returns:
        Dict with results or error
    """
    function = params.get('function', '')
    
    if function == 'get_article':
        docid = params.get('docid', '')
        
        if not docid:
            return {
                'error': 'Missing required parameter: docid',
                'error_code': 'MISSING_PARAM'
            }
        
        # Validate docid format (should be numeric string)
        if not docid.isdigit():
            # Try to extract docid from URL if provided
            url_match = re.search(r'docid=(\d+)', docid)
            if url_match:
                docid = url_match.group(1)
            else:
                return {
                    'error': 'Invalid docid format. Must be numeric ID or URL containing docid parameter.',
                    'error_code': 'INVALID_PARAM'
                }
        
        return await fetch_article_detail(docid)
    
    else:
        return {
            'error': f'Unknown function: {function}. Available: get_article',
            'error_code': 'UNKNOWN_FUNCTION'
        }