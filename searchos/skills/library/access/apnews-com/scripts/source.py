"""
AP News Access Skill

Fetches AP News articles and extracts structured content including:
- Title/headline
- Byline/authors
- Article body
- Publication/modification dates
- Keywords/tags
- Images

Uses JSON-LD structured data for metadata and HTML parsing for article body.
"""

import asyncio
import json
import re
from typing import Any
from urllib.parse import urljoin, urlparse, quote_plus

import aiohttp
from bs4 import BeautifulSoup


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute AP News article fetching or search.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with article data or search results
    """
    function = params.get("function", "")
    
    if function == "get_article":
        url = params.get("url", "").strip()
        if not url:
            return {"error": "Missing required parameter: url"}
        return await get_article(url)
    
    elif function == "search":
        query = params.get("query", "").strip()
        if not query:
            return {"error": "Missing required parameter: query"}
        max_results = params.get("max_results", 10)
        return await search_articles(query, max_results)
    
    else:
        return {"error": f"Unknown function: {function}. Use 'get_article' or 'search'."}


async def fetch_html(url: str, session: aiohttp.ClientSession) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X_10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            html = await resp.text()
            return resp.status, html
    except asyncio.TimeoutError:
        return 408, ""
    except Exception as e:
        return 500, str(e)


def extract_json_ld(html: str) -> list[dict]:
    """Extract all JSON-LD structured data from HTML."""
    pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
    matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
    
    results = []
    for match in matches:
        try:
            data = json.loads(match)
            # Normalize to list
            items = data if isinstance(data, list) else [data]
            results.extend(items)
        except json.JSONDecodeError:
            continue
    
    return results


def extract_article_from_json_ld(items: list[dict]) -> dict | None:
    """Extract NewsArticle data from JSON-LD items."""
    for item in items:
        if isinstance(item, dict) and item.get('@type') in ['NewsArticle', 'Article']:
            # Extract author names
            authors = []
            author_data = item.get('author', [])
            if isinstance(author_data, list):
                for auth in author_data:
                    if isinstance(auth, dict):
                        authors.append({
                            'name': auth.get('name', ''),
                            'url': auth.get('url', ''),
                            'job_title': auth.get('jobTitle', ''),
                        })
                    elif isinstance(auth, str):
                        authors.append({'name': auth})
            elif isinstance(author_data, dict):
                authors.append({
                    'name': author_data.get('name', ''),
                    'url': author_data.get('url', ''),
                    'job_title': author_data.get('jobTitle', ''),
                })
            elif isinstance(author_data, str):
                authors.append({'name': author_data})
            
            # Extract images
            images = []
            image_data = item.get('image', [])
            if isinstance(image_data, list):
                for img in image_data:
                    if isinstance(img, dict) and 'url' in img:
                        images.append({
                            'url': img.get('url', ''),
                            'width': img.get('width'),
                            'height': img.get('height'),
                        })
                    elif isinstance(img, str):
                        images.append({'url': img})
            elif isinstance(image_data, dict):
                images.append({
                    'url': image_data.get('url', ''),
                    'width': image_data.get('width'),
                    'height': image_data.get('height'),
                })
            elif isinstance(image_data, str):
                images.append({'url': image_data})
            
            return {
                'headline': item.get('headline', ''),
                'description': item.get('description', ''),
                'url': item.get('url', ''),
                'date_published': item.get('datePublished', ''),
                'date_modified': item.get('dateModified', ''),
                'authors': authors,
                'images': images,
                'publisher': item.get('publisher', {}).get('name', 'AP News') if isinstance(item.get('publisher'), dict) else item.get('publisher', 'AP News'),
                'keywords': item.get('keywords', []),
                'section': item.get('articleSection', []),
                'thumbnail_url': item.get('thumbnailUrl', ''),
            }
    
    return None


def extract_body_from_html(html: str) -> str:
    """Extract article body from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try RichTextStoryBody first (most reliable for AP News)
    body_div = soup.find('div', class_=re.compile(r'RichTextStoryBody'))
    if body_div:
        # Get all paragraphs
        paragraphs = body_div.find_all('p')
        if paragraphs:
            return '\n\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        # Fallback to full div text
        return body_div.get_text(strip=True, separator='\n')
    
    # Try Page-storyBody
    body_div = soup.find('div', class_=re.compile(r'Page-storyBody'))
    if body_div:
        # Find RichTextStoryBody inside
        rich_text = body_div.find('div', class_=re.compile(r'RichTextStoryBody'))
        if rich_text:
            paragraphs = rich_text.find_all('p')
            if paragraphs:
                return '\n\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
    
    # Try article tag
    article = soup.find('article')
    if article:
        paragraphs = article.find_all('p')
        if paragraphs:
            return '\n\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True) and len(p.get_text(strip=True)) > 50)
    
    return ""


def extract_meta_tags(html: str) -> dict:
    """Extract useful meta tags from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    meta_data = {}
    
    # Open Graph tags
    og_title = soup.find('meta', property='og:title')
    if og_title:
        meta_data['og_title'] = og_title.get('content', '')
    
    og_description = soup.find('meta', property='og:description')
    if og_description:
        meta_data['og_description'] = og_description.get('content', '')
    
    og_image = soup.find('meta', property='og:image')
    if og_image:
        meta_data['og_image'] = og_image.get('content', '')
    
    # Article meta
    article_author = soup.find('meta', property='article:author')
    if article_author:
        meta_data['article_author'] = article_author.get('content', '')
    
    article_published = soup.find('meta', property='article:published_time')
    if article_published:
        meta_data['article_published_time'] = article_published.get('content', '')
    
    article_modified = soup.find('meta', property='article:modified_time')
    if article_modified:
        meta_data['article_modified_time'] = article_modified.get('content', '')
    
    # Standard meta
    author = soup.find('meta', attrs={'name': 'author'})
    if author:
        meta_data['author'] = author.get('content', '')
    
    description = soup.find('meta', attrs={'name': 'description'})
    if description:
        meta_data['description'] = description.get('content', '')
    
    keywords = soup.find('meta', attrs={'name': 'keywords'})
    if keywords:
        meta_data['keywords'] = keywords.get('content', '')
    
    return meta_data


async def get_article(url: str) -> dict[str, Any]:
    """
    Fetch and extract article content from an AP News URL.
    
    Args:
        url: AP News article URL
    
    Returns:
        Dictionary with article data or error
    """
    # Validate URL
    parsed = urlparse(url)
    if not parsed.netloc or 'apnews.com' not in parsed.netloc:
        return {"error": "Invalid URL. Must be an AP News article URL (apnews.com)"}
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(url, session)
        
        if status != 200:
            return {
                "error": f"Failed to fetch article: HTTP {status}",
                "url": url,
            }
        
        # Check for error page
        if 'Page unavailable' in html or 'PAGE UNAVAILABLE' in html:
            return {
                "error": "Article not found or page unavailable",
                "url": url,
            }
        
        # Extract JSON-LD structured data
        json_ld_items = extract_json_ld(html)
        article_data = extract_article_from_json_ld(json_ld_items)
        
        # Extract article body from HTML
        body = extract_body_from_html(html)
        
        # Extract meta tags as fallback/supplement
        meta_data = extract_meta_tags(html)
        
        # Build result
        result = {
            "success": True,
            "url": url,
        }
        
        if article_data:
            result.update(article_data)
            result['source'] = 'json-ld'
        else:
            # Fallback to meta tags
            result['headline'] = meta_data.get('og_title', '')
            result['description'] = meta_data.get('og_description', meta_data.get('description', ''))
            result['date_published'] = meta_data.get('article_published_time', '')
            result['date_modified'] = meta_data.get('article_modified_time', '')
            result['authors'] = [{'name': meta_data.get('author', meta_data.get('article_author', ''))}] if meta_data.get('author') or meta_data.get('article_author') else []
            result['keywords'] = meta_data.get('keywords', '').split(',') if meta_data.get('keywords') else []
            result['source'] = 'meta-tags'
        
        # Add body
        if body:
            result['body'] = body
            result['body_length'] = len(body)
        else:
            result['body'] = ''
            result['body_length'] = 0
            result['body_warning'] = 'Could not extract article body'
        
        # Add meta data
        if meta_data.get('og_image'):
            if not result.get('images'):
                result['images'] = [{'url': meta_data['og_image']}]
        
        return result


async def search_articles(query: str, max_results: int = 10) -> dict[str, Any]:
    """
    Search for AP News articles.
    
    Note: AP News doesn't have a public search API, so we use their tag/topic pages
    or extract articles from category pages.
    
    Args:
        query: Search query
        max_results: Maximum number of results to return
    
    Returns:
        Dictionary with search results or error
    """
    # AP News search URL pattern
    search_url = f"https://apnews.com/search?q={quote_plus(query)}"
    
    async with aiohttp.ClientSession() as session:
        status, html = await fetch_html(search_url, session)
        
        if status != 200:
            return {
                "error": f"Search failed: HTTP {status}",
                "query": query,
            }
        
        # Extract article URLs from search results
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all article links
        article_urls = []
        seen_urls = set()
        
        # Look for links with /article/ in href
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if '/article/' in href:
                # Normalize URL
                if href.startswith('/'):
                    href = f"https://apnews.com{href}"
                elif not href.startswith('http'):
                    href = f"https://apnews.com/{href}"
                
                if href not in seen_urls:
                    seen_urls.add(href)
                    article_urls.append(href)
                    
                    if len(article_urls) >= max_results:
                        break
        
        if not article_urls:
            # Try alternative pattern - look for PagePromo links
            for link in soup.find_all('a', class_=re.compile(r'PagePromo', re.I)):
                href = link.get('href', '')
                if href and '/article/' in href:
                    if href.startswith('/'):
                        href = f"https://apnews.com{href}"
                    
                    if href not in seen_urls:
                        seen_urls.add(href)
                        article_urls.append(href)
                        
                        if len(article_urls) >= max_results:
                            break
        
        # Extract basic info for each article
        results = []
        for url in article_urls:
            # Try to extract title from link text or nearby elements
            link_elem = soup.find('a', href=lambda x: x and url.endswith(x.split('/')[-1]) if x else False)
            
            title = ""
            if link_elem:
                title = link_elem.get_text(strip=True)
            
            results.append({
                'url': url,
                'title': title if title else "Click to view article",
            })
        
        return {
            "success": True,
            "query": query,
            "total_results": len(results),
            "results": results,
            "note": "For full article content, use get_article with the URL",
        }