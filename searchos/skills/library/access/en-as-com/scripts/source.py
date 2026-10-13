"""
AS English (en.as.com) Sports News Access Skill

This skill provides access to AS English sports news, specifically:
- Article extraction with special handling for roster lists and structured content
- NBA section article listing

Target site: https://en.as.com
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the AS English skill.
    
    Dispatches to the appropriate function based on params['function'].
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await get_article(params)
    elif function == "list_articles":
        return await list_articles(params)
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": ["get_article", "list_articles"]
        }


async def _fetch_html(url: str, session: aiohttp.ClientSession) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch HTML content from a URL.
    
    Returns (html, error) tuple.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=30) as response:
            if response.status != 200:
                return None, f"HTTP {response.status}"
            html = await response.text()
            return html, None
    except asyncio.TimeoutError:
        return None, "Request timeout"
    except Exception as e:
        return None, str(e)


def _extract_roster_lists(soup: BeautifulSoup) -> dict[str, list[str]]:
    """
    Extract roster/player lists from AS.com articles.
    
    AS.com uses div.a_de_txt containers for roster sections.
    Each container has a preceding h2/h3 header and contains a ul/ol list.
    """
    rosters = {}
    
    # Find all content divs that contain roster lists
    content_divs = soup.find_all('div', class_='a_de_txt')
    
    for div in content_divs:
        # Get the preceding header
        prev_header = div.find_previous(['h2', 'h3'])
        if not prev_header:
            continue
        
        section_name = prev_header.get_text(strip=True)
        
        # Find lists inside this div
        lists = div.find_all(['ul', 'ol'])
        if not lists:
            continue
        
        # Combine all list items from this section
        items = []
        for lst in lists:
            for li in lst.find_all('li', recursive=False):
                item_text = li.get_text(strip=True)
                if item_text:
                    items.append(item_text)
        
        if items:
            rosters[section_name] = items
    
    return rosters


def _extract_article_metadata(soup: BeautifulSoup, url: str) -> dict[str, Any]:
    """
    Extract article metadata from meta tags and JSON-LD.
    """
    metadata = {
        "url": url,
        "title": None,
        "description": None,
        "author": None,
        "published_time": None,
        "modified_time": None,
        "image": None,
        "keywords": [],
    }
    
    # Extract from meta tags
    meta_mappings = {
        'title': ['og:title', 'twitter:title', 'title'],
        'description': ['og:description', 'twitter:description', 'description'],
        'author': ['author', 'article:author'],
        'published_time': ['article:published_time'],
        'modified_time': ['article:modified_time'],
        'image': ['og:image', 'twitter:image'],
    }
    
    for field, meta_names in meta_mappings.items():
        for meta_name in meta_names:
            meta = soup.find('meta', attrs={'property': meta_name}) or \
                   soup.find('meta', attrs={'name': meta_name})
            if meta and meta.get('content'):
                metadata[field] = meta.get('content').strip()
                break
    
    # Extract keywords
    keywords_meta = soup.find('meta', attrs={'name': 'keywords'})
    if keywords_meta and keywords_meta.get('content'):
        metadata['keywords'] = [k.strip() for k in keywords_meta.get('content').split(',') if k.strip()]
    
    # Try to get title from h1 if not in meta
    if not metadata['title']:
        h1 = soup.find('h1')
        if h1:
            metadata['title'] = h1.get_text(strip=True)
    
    # Extract from JSON-LD
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get('@type') == 'NewsArticle':
                        if item.get('headline') and not metadata['title']:
                            metadata['title'] = item.get('headline')
                        if item.get('datePublished') and not metadata['published_time']:
                            metadata['published_time'] = item.get('datePublished')
                        if item.get('author') and not metadata['author']:
                            author = item.get('author')
                            if isinstance(author, dict):
                                metadata['author'] = author.get('name')
                            elif isinstance(author, list) and author:
                                metadata['author'] = author[0].get('name') if isinstance(author[0], dict) else str(author[0])
                        break
            elif isinstance(data, dict) and data.get('@type') == 'NewsArticle':
                if data.get('headline') and not metadata['title']:
                    metadata['title'] = data.get('headline')
                if data.get('datePublished') and not metadata['published_time']:
                    metadata['published_time'] = data.get('datePublished')
        except:
            pass
    
    return metadata


def _extract_article_body(soup: BeautifulSoup) -> dict[str, Any]:
    """
    Extract article body content including text and structured lists.
    """
    content = {
        "paragraphs": [],
        "headers": [],
        "lists": {},
        "rosters": {},
    }
    
    article = soup.find('article')
    if not article:
        return content
    
    # Extract roster lists (special handling for player rosters)
    content["rosters"] = _extract_roster_lists(article)
    
    # Find the article body
    body = article.find('div', class_='a_de') or article
    
    # Extract headers, paragraphs, and lists in order
    for elem in body.find_all(['h2', 'h3', 'p', 'ul', 'ol'], recursive=True):
        if elem.name in ['h2', 'h3']:
            text = elem.get_text(strip=True)
            if text and len(text) < 500:
                # Skip navigation/related content headers
                if not any(skip in text.lower() for skip in ['related stories', 'most viewed', 'recommended', 'subscribe', 'follow us']):
                    content["headers"].append({
                        "level": int(elem.name[1]),
                        "text": text
                    })
        
        elif elem.name == 'p':
            text = elem.get_text(strip=True)
            if text and len(text) > 20:  # Skip very short paragraphs
                # Skip if it's inside a list item
                if not elem.find_parent('li'):
                    content["paragraphs"].append(text)
        
        elif elem.name in ['ul', 'ol']:
            # Check if this is a roster list (in a_de_txt div)
            parent_div = elem.find_parent('div', class_='a_de_txt')
            if parent_div:
                # Already captured in rosters
                continue
            
            # Skip navigation/utility lists
            parent_classes = elem.parent.get('class', []) if elem.parent else []
            if any(skip in ' '.join(parent_classes).lower() for skip in ['nav', 'menu', 'footer', 'social', 'share', 'w_eds', 'msh']):
                continue
            
            items = [li.get_text(strip=True) for li in elem.find_all('li', recursive=False) if li.get_text(strip=True)]
            if items:
                # Get preceding header if any
                prev_header = elem.find_previous(['h2', 'h3'])
                list_name = prev_header.get_text(strip=True) if prev_header else f"list_{len(content['lists']) + 1}"
                content["lists"][list_name] = items
    
    return content


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract article content from an AS English article URL.
    
    Parameters:
        url (required): The article URL to extract content from
        include_rosters (optional): Whether to include roster lists (default: true)
        include_body (optional): Whether to include full body content (default: true)
    
    Returns:
        Article metadata and content including any roster/player lists found.
    """
    url = params.get("url")
    if not url:
        return {"error": "Missing required parameter: url"}
    
    # Validate URL
    parsed = urlparse(url)
    if not parsed.netloc:
        return {"error": "Invalid URL: missing domain"}
    
    include_rosters = params.get("include_rosters", "true").lower() != "false"
    include_body = params.get("include_body", "true").lower() != "false"
    
    async with aiohttp.ClientSession() as session:
        html, error = await _fetch_html(url, session)
        if error:
            return {"error": f"Failed to fetch article: {error}"}
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract metadata
    metadata = _extract_article_metadata(soup, url)
    
    result = {
        "success": True,
        "article": metadata
    }
    
    # Extract body content
    if include_body:
        body = _extract_article_body(soup)
        
        # Separate rosters if requested
        if include_rosters and body.get("rosters"):
            result["rosters"] = body["rosters"]
        
        result["content"] = {
            "headers": body.get("headers", []),
            "paragraphs": body.get("paragraphs", []),
            "lists": body.get("lists", {})
        }
    
    # Check if we found any content
    if not metadata.get("title") and not result.get("content", {}).get("paragraphs"):
        result["warning"] = "Could not extract article content"
    
    return result


async def list_articles(params: dict[str, Any]) -> dict[str, Any]:
    """
    List NBA articles from AS English.
    
    Parameters:
        limit (optional): Maximum number of articles to return (default: 20, max: 50)
    
    Returns:
        List of articles with URL, title, and basic metadata.
    """
    limit = min(int(params.get("limit", 20)), 50)
    url = "https://en.as.com/nba/"
    
    async with aiohttp.ClientSession() as session:
        html, error = await _fetch_html(url, session)
        if error:
            return {"error": f"Failed to fetch NBA section: {error}"}
    
    soup = BeautifulSoup(html, 'html.parser')
    
    articles = []
    
    # Method 1: Extract from JSON-LD (most reliable for URLs)
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'ItemList':
                items = data.get('itemListElement', [])
                for item in items:
                    if isinstance(item, dict) and item.get('url'):
                        articles.append({
                            "url": item.get('url'),
                            "position": item.get('position'),
                        })
        except:
            pass
    
    # Method 2: Extract from article tags for additional metadata
    article_data = {}
    for article in soup.find_all('article'):
        link = article.find('a', href=True)
        if link:
            href = link.get('href', '')
            title = link.get_text(strip=True)
            
            # Get image
            img = article.find('img')
            image_url = None
            if img:
                image_url = img.get('src') or img.get('data-src')
            
            # Get timestamp if available
            time_elem = article.find('time')
            timestamp = time_elem.get('datetime') if time_elem else None
            
            article_data[href] = {
                "title": title,
                "image_url": image_url,
                "timestamp": timestamp
            }
    
    # Merge the data
    results = []
    for article in articles[:limit]:
        article_url = article.get('url')
        result = {
            "url": article_url,
            "position": article.get('position')
        }
        
        # Add metadata from article tags
        if article_url in article_data:
            result.update(article_data[article_url])
        
        results.append(result)
    
    # If JSON-LD didn't work, fall back to article tags only
    if not results:
        for href, data in list(article_data.items())[:limit]:
            if '/nba/' in href:
                results.append({
                    "url": href,
                    **data
                })
    
    return {
        "success": True,
        "section": "NBA",
        "section_url": url,
        "count": len(results),
        "articles": results
    }


# For testing
if __name__ == "__main__":
    async def test():
        print("=== Testing get_article ===")
        result = await execute({
            "function": "get_article",
            "url": "https://en.as.com/nba/2024-nba-all-star-game-rosters-full-list-of-players-for-both-teams-n/"
        })
        print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
        
        print("\n\n=== Testing list_articles ===")
        result = await execute({
            "function": "list_articles",
            "limit": 5
        })
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())