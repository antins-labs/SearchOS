"""
BuzzFeed Access Skill

Extracts structured content from BuzzFeed articles, with specialized support for
checklist/quiz content (e.g., TV show rankings, movie lists, etc.).

The skill parses the __NEXT_DATA__ JSON embedded in BuzzFeed pages to extract:
- Article metadata (title, author, publish date, tags)
- Checklist items with names, years, images, and credits
- Quiz questions and answers
"""

import asyncio
import json
import re
from typing import Any
from datetime import datetime

import aiohttp


async def fetch_page(url: str) -> tuple[int, str]:
    """Fetch a BuzzFeed page and return (status_code, html)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            html = await resp.text()
            return resp.status, html


def extract_next_data(html: str) -> dict | None:
    """Extract the __NEXT_DATA__ JSON from BuzzFeed HTML."""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def parse_checklist_item(text: str) -> dict:
    """
    Parse a checklist item text to extract name and year.
    
    Examples:
        "_Planet Earth II_ (2016)" -> {"name": "Planet Earth II", "year": 2016}
        "_Game of Thrones_ (2011)" -> {"name": "Game of Thrones", "year": 2011}
        "The Civil War (1990)" -> {"name": "The Civil War", "year": 1990}
    """
    # Pattern 1: _Title_ (Year) - italicized title with underscores
    match = re.match(r'_([^_]+)_[^\d]*(\d{4})', text)
    if match:
        return {
            "name": match.group(1).strip(),
            "year": int(match.group(2))
        }
    
    # Pattern 2: Title (Year) - plain title without formatting
    match = re.match(r'([^(]+)\s*\((\d{4})\)', text)
    if match:
        return {
            "name": match.group(1).strip(),
            "year": int(match.group(2))
        }
    
    # Fallback: just clean up the text
    return {
        "name": text.replace('_', '').strip(),
        "year": None
    }


def parse_timestamp(ts) -> str | None:
    """Parse a timestamp that could be string or int."""
    if ts is None:
        return None
    try:
        # Handle string timestamps
        if isinstance(ts, str):
            ts = int(ts)
        return datetime.utcfromtimestamp(ts).isoformat() + 'Z'
    except (TypeError, ValueError, OSError):
        return None


def extract_article_metadata(buzz: dict) -> dict:
    """Extract article metadata from the buzz object."""
    bylines = buzz.get('bylines', [])
    author = None
    author_url = None
    
    if bylines and isinstance(bylines, list) and len(bylines) > 0:
        byline = bylines[0]
        if isinstance(byline, dict):
            author = byline.get('display_name')
            author_url = byline.get('twitter_page_url') or f"https://www.buzzfeed.com/{byline.get('username', '')}"
    
    if not author:
        author = buzz.get('username')
        author_url = f"https://www.buzzfeed.com/{author}" if author else None
    
    published_date = parse_timestamp(buzz.get('published'))
    
    images = buzz.get('images', {}) or {}
    
    return {
        "id": buzz.get('id'),
        "title": buzz.get('title'),
        "description": buzz.get('description'),
        "author": author,
        "author_url": author_url,
        "published": published_date,
        "category": buzz.get('category'),
        "language": buzz.get('language'),
        "country": buzz.get('country_code'),
        "canonical_url": buzz.get('canonical_url'),
        "tags": buzz.get('tags', []) or [],
        "is_quiz": buzz.get('isQuiz') or buzz.get('is_quiz'),
        "is_checklist": buzz.get('isChecklist'),
        "is_trivia": buzz.get('isTrivia'),
        "is_personality": buzz.get('isPersonality'),
        "image": images.get('standard'),
        "image_wide": images.get('wide'),
    }


def extract_checklist_items(buzz: dict) -> list[dict]:
    """
    Extract checklist items from a BuzzFeed checklist/quiz article.
    
    Returns a list of items with:
    - id: numeric identifier
    - name: item name (parsed from text)
    - year: year (if extractable)
    - original_text: raw text from BuzzFeed
    - image_url: associated image URL
    - image_credit: image credit/source
    """
    items = []
    sub_buzzes = buzz.get('sub_buzzes', []) or []
    
    for sub_buzz in sub_buzzes:
        bfp_data = sub_buzz.get('bfp_data', {}) or {}
        data = bfp_data.get('data', {}) or {}
        questions = data.get('questions', []) or []
        
        for question in questions:
            answers = question.get('answers', []) or []
            for answer in answers:
                text = answer.get('text', '')
                parsed = parse_checklist_item(text)
                
                media = answer.get('media', {}) or {}
                
                item = {
                    "id": answer.get('id'),
                    "name": parsed['name'],
                    "year": parsed['year'],
                    "original_text": text,
                    "image_url": media.get('url'),
                    "image_credit": media.get('credit'),
                }
                items.append(item)
    
    return items


def extract_quiz_results(buzz: dict) -> list[dict]:
    """
    Extract quiz result options from a BuzzFeed personality quiz.
    """
    results = []
    sub_buzzes = buzz.get('sub_buzzes', []) or []
    
    for sub_buzz in sub_buzzes:
        bfp_data = sub_buzz.get('bfp_data', {}) or {}
        data = bfp_data.get('data', {}) or {}
        
        # Quiz results
        quiz_results = data.get('results', []) or []
        for result in quiz_results:
            results.append({
                "id": result.get('id'),
                "title": result.get('title'),
                "description": result.get('description'),
                "image_url": result.get('image', {}).get('url') if result.get('image') else None,
            })
    
    return results


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a BuzzFeed article and extract its metadata.
    
    Parameters:
        url: The BuzzFeed article URL
    
    Returns:
        Article metadata including title, author, publish date, tags, etc.
    """
    url = params.get('url')
    if not url:
        return {"error": "Missing required parameter: url", "success": False}
    
    if 'buzzfeed.com' not in url:
        return {"error": "URL must be from buzzfeed.com", "success": False}
    
    try:
        status, html = await fetch_page(url)
        
        if status != 200:
            return {
                "error": f"Failed to fetch page: HTTP {status}",
                "success": False,
                "status_code": status
            }
        
        data = extract_next_data(html)
        if not data:
            return {
                "error": "Could not extract page data (no __NEXT_DATA__ found)",
                "success": False
            }
        
        buzz = data.get('props', {}).get('pageProps', {}).get('buzz', {})
        if not buzz:
            return {
                "error": "Could not find article data in page",
                "success": False
            }
        
        metadata = extract_article_metadata(buzz)
        metadata['success'] = True
        
        return metadata
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "success": False}
    except Exception as e:
        return {"error": f"Failed to fetch article: {str(e)}", "success": False}


async def get_checklist(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract checklist items from a BuzzFeed checklist/quiz article.
    
    Parameters:
        url: The BuzzFeed checklist/quiz URL
        include_metadata: Whether to include article metadata (default: true)
    
    Returns:
        List of checklist items with names, years, images, and article metadata.
    """
    url = params.get('url')
    if not url:
        return {"error": "Missing required parameter: url", "success": False}
    
    if 'buzzfeed.com' not in url:
        return {"error": "URL must be from buzzfeed.com", "success": False}
    
    include_metadata = params.get('include_metadata', True)
    
    try:
        status, html = await fetch_page(url)
        
        if status != 200:
            return {
                "error": f"Failed to fetch page: HTTP {status}",
                "success": False,
                "status_code": status
            }
        
        data = extract_next_data(html)
        if not data:
            return {
                "error": "Could not extract page data (no __NEXT_DATA__ found)",
                "success": False
            }
        
        buzz = data.get('props', {}).get('pageProps', {}).get('buzz', {})
        if not buzz:
            return {
                "error": "Could not find article data in page",
                "success": False
            }
        
        items = extract_checklist_items(buzz)
        
        result = {
            "success": True,
            "item_count": len(items),
            "items": items,
        }
        
        if include_metadata:
            result['article'] = extract_article_metadata(buzz)
        
        return result
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "success": False}
    except Exception as e:
        return {"error": f"Failed to fetch checklist: {str(e)}", "success": False}


async def get_quiz_results(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract quiz result options from a BuzzFeed personality quiz.
    
    Parameters:
        url: The BuzzFeed quiz URL
        include_metadata: Whether to include article metadata (default: true)
    
    Returns:
        List of possible quiz results with titles, descriptions, and images.
    """
    url = params.get('url')
    if not url:
        return {"error": "Missing required parameter: url", "success": False}
    
    if 'buzzfeed.com' not in url:
        return {"error": "URL must be from buzzfeed.com", "success": False}
    
    include_metadata = params.get('include_metadata', True)
    
    try:
        status, html = await fetch_page(url)
        
        if status != 200:
            return {
                "error": f"Failed to fetch page: HTTP {status}",
                "success": False,
                "status_code": status
            }
        
        data = extract_next_data(html)
        if not data:
            return {
                "error": "Could not extract page data (no __NEXT_DATA__ found)",
                "success": False
            }
        
        buzz = data.get('props', {}).get('pageProps', {}).get('buzz', {})
        if not buzz:
            return {
                "error": "Could not find article data in page",
                "success": False
            }
        
        results = extract_quiz_results(buzz)
        
        result = {
            "success": True,
            "result_count": len(results),
            "results": results,
        }
        
        if include_metadata:
            result['article'] = extract_article_metadata(buzz)
        
        return result
        
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "success": False}
    except Exception as e:
        return {"error": f"Failed to fetch quiz: {str(e)}", "success": False}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute BuzzFeed skill functions.
    
    Dispatches based on params['function']:
        - get_article: Fetch article metadata
        - get_checklist: Extract checklist items from a quiz/checklist
        - get_quiz_results: Extract quiz result options
    """
    function = params.get('function')
    
    if function == 'get_article':
        return await get_article(params)
    elif function == 'get_checklist':
        return await get_checklist(params)
    elif function == 'get_quiz_results':
        return await get_quiz_results(params)
    else:
        return {
            "error": f"Unknown function: {function}. Available: get_article, get_checklist, get_quiz_results",
            "success": False
        }