"""
SearchOS access skill for finance.sina.com.cn stock news articles.

This module provides access to Sina Finance news articles, extracting structured
data including article content, metadata, images, and TOP50 ranking information.
"""

import asyncio
import re
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
from urllib.parse import urlparse


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute function for Sina Finance article extraction.
    
    Args:
        params: Dictionary containing:
            - function: The operation to perform
            - url: Article URL (for get_article)
            - include_images: Whether to extract images (default: true)
            - include_content: Whether to extract full content (default: true)
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with extracted data or error information
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await get_article(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_article"]
        }


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract article content from a Sina Finance URL.
    
    Args:
        params: Dictionary containing:
            - url: The article URL (required)
            - include_images: Whether to extract images (default: true)
            - include_content: Whether to extract full content (default: true)
    
    Returns:
        Dictionary with article data or error information
    """
    url = params.get("url", "")
    include_images = params.get("include_images", True)
    include_content = params.get("include_content", True)
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url"
        }
    
    # Validate URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    
    parsed = urlparse(url)
    if "sina.com.cn" not in parsed.netloc:
        return {
            "success": False,
            "error": "URL must be from sina.com.cn domain"
        }
    
    # Extract article ID from URL
    article_id_match = re.search(r'doc-([a-z0-9]+)\.shtml', url)
    article_id = article_id_match.group(1) if article_id_match else None
    
    # Fetch article
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    return {
                        "success": False,
                        "error": "Article not found (404)",
                        "url": url,
                        "article_id": article_id
                    }
                
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP error: {response.status}",
                        "url": url,
                        "article_id": article_id
                    }
                
                html = await response.text()
                
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timeout",
            "url": url,
            "article_id": article_id
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "url": url,
            "article_id": article_id
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "url": url,
            "article_id": article_id
        }
    
    # Parse HTML
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Check if article exists
        artibody = soup.find(id='artibody')
        if not artibody:
            return {
                "success": False,
                "error": "Article content not found (no #artibody element)",
                "url": url,
                "article_id": article_id
            }
        
        # Initialize article data
        article_data = {
            "success": True,
            "url": url,
            "article_id": article_id,
            "title": None,
            "description": None,
            "keywords": [],
            "author": None,
            "source": None,
            "published_time": None,
            "updated_time": None,
            "category": None,
            "content": None,
            "paragraphs": [],
            "images": [],
            "content_length": 0,
            "paragraph_count": 0,
            "image_count": 0
        }
        
        # Extract title
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Remove site suffix (e.g., "|物业_新浪财经_新浪网")
            title = re.split(r'[|_]', title)[0].strip()
            article_data["title"] = title
        
        # Extract meta information
        meta_mapping = {
            'description': ('meta', {'name': 'description'}),
            'keywords': ('meta', {'name': 'keywords'}),
            'author': ('meta', {'property': 'article:author'}),
            'published_time': ('meta', {'property': 'article:published_time'}),
            'updated_time': ('meta', {'property': 'article:modified_time'})
        }
        
        for field, (tag, attrs) in meta_mapping.items():
            elem = soup.find(tag, attrs)
            if elem:
                content = elem.get('content', '')
                if field == 'keywords':
                    article_data[field] = [k.strip() for k in content.split(',') if k.strip()]
                else:
                    article_data[field] = content
        
        # Sina-specific Weibo meta tags
        weibo_create = soup.find('meta', attrs={'name': 'weibo:article:create_at'})
        if weibo_create:
            article_data["published_time"] = weibo_create.get('content')
        
        weibo_update = soup.find('meta', attrs={'name': 'weibo:article:update_at'})
        if weibo_update:
            article_data["updated_time"] = weibo_update.get('content')
        
        # Extract source
        source_elem = (
            soup.find('span', class_='source') or 
            soup.find('a', class_='source') or
            soup.find('span', class_='ent-source') or
            soup.find('span', {'id': 'author_ename'})
        )
        if source_elem:
            article_data["source"] = source_elem.get_text(strip=True)
        
        # If no source found, use author
        if not article_data["source"] and article_data["author"]:
            article_data["source"] = article_data["author"]
        
        # Extract category from URL
        if '/stock/' in url:
            article_data["category"] = "stock"
            if '/hk/' in url:
                article_data["category"] = "stock_hk"
            elif '/us/' in url:
                article_data["category"] = "stock_us"
            elif '/sh/' in url:
                article_data["category"] = "stock_sh"
            elif '/sz/' in url:
                article_data["category"] = "stock_sz"
        elif '/forex/' in url:
            article_data["category"] = "forex"
        elif '/future/' in url:
            article_data["category"] = "future"
        elif '/fund/' in url:
            article_data["category"] = "fund"
        
        # Extract content
        if include_content:
            # Get full text
            article_data["content"] = artibody.get_text(strip=True, separator='\n')
            article_data["content_length"] = len(article_data["content"])
            
            # Get individual paragraphs
            paragraphs = artibody.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text:
                    article_data["paragraphs"].append(text)
            
            article_data["paragraph_count"] = len(article_data["paragraphs"])
        
        # Extract images
        if include_images:
            images = artibody.find_all('img')
            for img in images:
                src = img.get('src') or img.get('data-src')
                if src:
                    # Normalize URL
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif not src.startswith('http'):
                        src = 'https://finance.sina.com.cn' + src
                    
                    article_data["images"].append({
                        "url": src,
                        "alt": img.get('alt', ''),
                        "title": img.get('title', '')
                    })
            
            article_data["image_count"] = len(article_data["images"])
        
        # Filter out empty fields
        article_data = {k: v for k, v in article_data.items() if v or k in ['success', 'url', 'article_id']}
        
        return article_data
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Parse error: {str(e)}",
            "url": url,
            "article_id": article_id
        }