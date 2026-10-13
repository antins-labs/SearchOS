"""
SearchOS access skill for zwgk.mct.gov.cn (文化和旅游部政府信息公开)
Ministry of Culture and Tourism of the People's Republic of China - Government Information Disclosure

This skill extracts official government announcements, particularly 5A scenic area designations.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional
from urllib.parse import urljoin
from datetime import datetime


# Constants
BASE_URL = "https://zwgk.mct.gov.cn"
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}

# Timeout configuration
DEFAULT_TIMEOUT = 30


def clean_title(title: str) -> str:
    """Remove HTML tags from title"""
    if not title:
        return ""
    # Remove any HTML tags
    title = re.sub(r'<[^>]+>', '', title)
    # Clean whitespace
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def extract_scenic_areas(text: str) -> list[dict]:
    """
    Extract scenic area names from document content.
    Handles both numbered list format and paragraph format.
    """
    scenic_areas = []
    lines = text.split('\n')
    
    # Chinese province/municipality/autonomous region prefixes
    province_pattern = r'^[京津冀晋内蒙古辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤港澳桂琼川贵云渝藏陕甘青宁新]'
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Pattern 1: numbered list (1.xxx, 2.xxx, 1、xxx, 1.xxx)
        match = re.match(r'^(\d+)\s*[\.\、\．]\s*(.+)$', line)
        if match:
            name = match.group(2).strip()
            if len(name) > 3 and '旅游景区' in name or '景区' in name or '旅游区' in name:
                scenic_areas.append({
                    'number': int(match.group(1)),
                    'name': name
                })
            continue
        
        # Pattern 2: Lines starting with province names (unnumbered format)
        if re.match(province_pattern, line):
            # Check if it looks like a scenic area name
            if len(line) > 5 and ('景区' in line or '旅游区' in line or '旅游' in line):
                # Avoid adding duplicates or non-scenic lines
                if '公告' not in line and '特此' not in line:
                    scenic_areas.append({
                        'number': len(scenic_areas) + 1,
                        'name': line
                    })
    
    return scenic_areas


def parse_document_metadata(soup: BeautifulSoup) -> dict:
    """Extract metadata from the document header"""
    metadata = {}
    
    # Extract meta tags
    for meta in soup.find_all('meta'):
        name = meta.get('name') or meta.get('property')
        content = meta.get('content')
        if name and content:
            metadata[name] = content
    
    # Clean the title
    if 'ArticleTitle' in metadata:
        metadata['ArticleTitle'] = clean_title(metadata['ArticleTitle'])
    
    # Parse content_head table for structured data
    content_head = soup.find(class_='content_head')
    if content_head:
        # Get all text and extract key-value pairs
        text = content_head.get_text('\n', strip=True)
        
        # Extract index number (索引号)
        index_match = re.search(r'索引号[：:\s]*([A-Z0-9\-]+)', text)
        if index_match:
            metadata['index_number'] = index_match.group(1).strip()
        
        # Extract document number (文号)
        docnum_match = re.search(r'文号[：:\s]*([^\n]+?)(?:\n|$|发布)', text)
        if docnum_match:
            metadata['doc_number'] = docnum_match.group(1).strip()
        
        # Extract organization (发布机构)
        org_match = re.search(r'发布机构[：:\s]*([^\n]+)', text)
        if org_match:
            metadata['organization'] = org_match.group(1).strip()
        
        # Extract date (发布日期)
        date_match = re.search(r'发布日期[：:\s]*(\d{4}-\d{2}-\d{2})', text)
        if date_match:
            metadata['publish_date'] = date_match.group(1)
        
        # Extract category (分类)
        cat_match = re.search(r'分类[：:\s]*([^\n]+)', text)
        if cat_match:
            metadata['category'] = cat_match.group(1).strip()
        
        # Extract keywords (主题词)
        kw_match = re.search(r'主题词[：:\s]*([^\n]+)', text)
        if kw_match:
            metadata['keywords'] = kw_match.group(1).strip()
    
    return metadata


def parse_document_content(soup: BeautifulSoup, url: str) -> dict:
    """Extract main content from the document"""
    content_div = soup.find(class_='gsj_htmlcon')
    if not content_div:
        # Try alternative selectors
        content_div = soup.find(class_='gsj_htmlcon_bot')
    
    result = {
        'content_text': '',
        'content_html': '',
        'scenic_areas': []
    }
    
    if content_div:
        # Get text content
        text = content_div.get_text('\n', strip=True)
        result['content_text'] = text
        
        # Get HTML (limited)
        result['content_html'] = str(content_div)[:5000]
        
        # Extract scenic areas
        result['scenic_areas'] = extract_scenic_areas(text)
    
    # Extract attachments
    attachments = []
    base_url = url.rsplit('/', 1)[0] + '/' if '/' in url else url
    
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Check for file extensions
        if any(ext in href.lower() for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar']):
            attachments.append({
                'url': urljoin(base_url, href) if not href.startswith('http') else href,
                'name': text
            })
        # Check for "附件" keyword
        elif '附件' in text and href:
            attachments.append({
                'url': urljoin(base_url, href) if not href.startswith('http') else href,
                'name': text
            })
    
    result['attachments'] = attachments
    
    return result


async def fetch_document(url: str, session: aiohttp.ClientSession) -> dict:
    """Fetch and parse a single document"""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)) as response:
            if response.status != 200:
                return {
                    'success': False,
                    'error': f'HTTP {response.status}',
                    'url': url
                }
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Parse metadata
            metadata = parse_document_metadata(soup)
            
            # Parse content
            content = parse_document_content(soup, url)
            
            # Build result
            result = {
                'success': True,
                'url': url,
                'title': metadata.get('ArticleTitle', ''),
                'publish_date': metadata.get('PubDate', metadata.get('publish_date', '')),
                'organization': metadata.get('ContentSource', metadata.get('organization', '')),
                'index_number': metadata.get('index_number', ''),
                'doc_number': metadata.get('doc_number', ''),
                'category': metadata.get('category', ''),
                'keywords': metadata.get('keywords', ''),
                'column_name': metadata.get('ColumnName', ''),
                'content_text': content['content_text'],
                'content_html': content['content_html'],
                'scenic_areas': content['scenic_areas'],
                'scenic_area_count': len(content['scenic_areas']),
                'attachments': content.get('attachments', []),
                'metadata': metadata
            }
            
            return result
            
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timeout',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url
        }


async def fetch_listing(category: str, session: aiohttp.ClientSession) -> dict:
    """Fetch listing page and extract document links"""
    url = f"{BASE_URL}/zfxxgkml/"
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)) as response:
            if response.status != 200:
                return {
                    'success': False,
                    'error': f'HTTP {response.status}',
                    'url': url
                }
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find all document links
            all_links = soup.find_all('a', href=True)
            documents = []
            seen_urls = set()
            
            for link in all_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Match document URL patterns: /YYYYMM/tYYYYMMDD_XXXXXX.html
                if re.search(r'/\d{6}/t\d{8}_\d+\.html?$', href):
                    full_url = urljoin(BASE_URL + '/zfxxgkml/', href)
                    
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        
                        # Extract category from URL
                        cat_match = re.match(r'.*/([^/]+)/\d{6}/t\d{8}_\d+\.html?$', full_url)
                        doc_category = cat_match.group(1) if cat_match else ''
                        
                        documents.append({
                            'url': full_url,
                            'title': text,
                            'category': doc_category
                        })
            
            # Filter by category if specified
            if category:
                documents = [d for d in documents if d['category'] == category]
            
            # Group by category for metadata
            categories = {}
            for doc in documents:
                cat = doc['category']
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append({
                    'url': doc['url'],
                    'title': doc['title']
                })
            
            return {
                'success': True,
                'url': url,
                'total_documents': len(documents),
                'documents': documents[:100],  # Limit to first 100
                'categories': {cat: len(docs) for cat, docs in categories.items()}
            }
            
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timeout',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url
        }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the skill.
    
    Parameters:
    - function: The operation to perform:
        - 'fetch_document': Fetch a single document by URL
        - 'fetch_documents': Fetch multiple documents by URLs
        - 'list_documents': List available documents (optionally filtered by category)
    
    For 'fetch_document':
        - url: The document URL (required)
    
    For 'fetch_documents':
        - urls: List of document URLs (required)
    
    For 'list_documents':
        - category: Optional category filter (e.g., 'zykf' for 资源开发)
        - limit: Maximum number of results (default: 50)
    """
    function = params.get('function', 'fetch_document')
    
    async with aiohttp.ClientSession(headers=DEFAULT_HEADERS) as session:
        if function == 'fetch_document':
            url = params.get('url')
            if not url:
                return {
                    'success': False,
                    'error': 'URL parameter is required for fetch_document function'
                }
            
            # Validate URL
            if not url.startswith(('http://', 'https://')):
                url = urljoin(BASE_URL, url)
            
            result = await fetch_document(url, session)
            return result
        
        elif function == 'fetch_documents':
            urls = params.get('urls', [])
            if not urls:
                return {
                    'success': False,
                    'error': 'URLs parameter is required for fetch_documents function'
                }
            
            # Validate and normalize URLs
            valid_urls = []
            for url in urls:
                if not url.startswith(('http://', 'https://')):
                    url = urljoin(BASE_URL, url)
                valid_urls.append(url)
            
            # Fetch documents concurrently
            tasks = [fetch_document(url, session) for url in valid_urls]
            results = await asyncio.gather(*tasks)
            
            # Summarize results
            successful = [r for r in results if r.get('success')]
            failed = [r for r in results if not r.get('success')]
            
            return {
                'success': True,
                'total': len(results),
                'successful': len(successful),
                'failed': len(failed),
                'documents': successful,
                'errors': failed if failed else None
            }
        
        elif function == 'list_documents':
            category = params.get('category', '')
            limit = params.get('limit', 50)
            
            result = await fetch_listing(category, session)
            
            if result.get('success'):
                # Apply limit
                if limit and len(result['documents']) > limit:
                    result['documents'] = result['documents'][:limit]
                
                result['limited_to'] = limit if limit else None
            
            return result
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Available functions: fetch_document, fetch_documents, list_documents'
            }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        print("Testing list_documents...")
        result = await execute({'function': 'list_documents', 'limit': 10})
        print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
        
        print("\n\nTesting fetch_document...")
        result = await execute({
            'function': 'fetch_document',
            'url': 'https://zwgk.mct.gov.cn/zfxxgkml/zykf/202412/t20241227_957450.html'
        })
        print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
    
    asyncio.run(test())