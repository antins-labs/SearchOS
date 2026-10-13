"""
Yahoo Sports (sports.yahoo.com) access skill.

Handles:
- Article pages: Extract headline, description, author, date, keywords
- NBA main page: Extract page info and article links
- NBA players page: Extract player listings

Uses Playwright with timeout handling since Yahoo has aggressive anti-bot measures.
"""

import asyncio
import re
import json
from typing import Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def _fetch_page_with_playwright(url: str, timeout_ms: int = 10000) -> dict:
    """
    Fetch a page using Playwright with timeout handling.
    Returns extracted data from meta tags and page content.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                java_script_enabled=True
            )
            
            page = await context.new_page()
            
            # Try to navigate with timeout
            try:
                await page.goto(url, timeout=timeout_ms, wait_until='domcontentloaded')
            except PlaywrightTimeoutError:
                pass  # Continue with partial content
            
            # Wait briefly for JS to render
            await asyncio.sleep(2)
            
            # Extract all available data
            data = await page.evaluate('''() => {
                const result = {
                    url: window.location.href,
                    title: document.title,
                    meta: {},
                    jsonLd: [],
                    links: [],
                    headings: [],
                    bodyText: ''
                };
                
                // Extract meta tags
                document.querySelectorAll('meta').forEach(meta => {
                    const name = meta.getAttribute('name') || meta.getAttribute('property') || meta.getAttribute('itemprop');
                    const content = meta.getAttribute('content');
                    if (name && content) {
                        result.meta[name] = content;
                    }
                });
                
                // Extract JSON-LD
                document.querySelectorAll('script[type="application/ld+json"]').forEach(script => {
                    try {
                        result.jsonLd.push(JSON.parse(script.textContent));
                    } catch(e) {}
                });
                
                // Extract article links (for listing pages)
                document.querySelectorAll('a[href$=".html"]').forEach(a => {
                    const href = a.href;
                    const text = a.textContent.trim();
                    if (text && href && !result.links.some(l => l.href === href)) {
                        result.links.push({ href, text: text.substring(0, 200) });
                    }
                });
                
                // Extract headings
                document.querySelectorAll('h1, h2, h3').forEach(h => {
                    const text = h.textContent.trim();
                    if (text) {
                        result.headings.push({
                            tag: h.tagName,
                            text: text.substring(0, 200)
                        });
                    }
                });
                
                // Extract main content text (limited)
                const article = document.querySelector('article, .caas-body, [data-testid="article-body"], main');
                if (article) {
                    result.bodyText = article.textContent.trim().substring(0, 5000);
                }
                
                return result;
            }''')
            
            return data
            
        finally:
            await browser.close()


def _extract_article_data(page_data: dict) -> dict:
    """Extract article information from page data."""
    meta = page_data.get('meta', {})
    
    article = {
        'url': page_data.get('url', ''),
        'title': page_data.get('title', ''),
        'headline': meta.get('og:title', meta.get('twitter:title', '')),
        'description': meta.get('description', meta.get('og:description', meta.get('twitter:description', ''))),
        'image': meta.get('og:image', meta.get('twitter:image', '')),
        'author': meta.get('author', ''),
        'published_time': meta.get('article:published_time', ''),
        'modified_time': meta.get('article:modified_time', ''),
        'keywords': meta.get('keywords', ''),
        'site_name': meta.get('og:site_name', ''),
        'type': meta.get('og:type', ''),
    }
    
    # Parse keywords
    if article['keywords']:
        article['keywords_list'] = [k.strip() for k in article['keywords'].split(',') if k.strip()]
    
    # Extract from JSON-LD if available
    for ld in page_data.get('jsonLd', []):
        if isinstance(ld, list):
            for item in ld:
                if isinstance(item, dict) and item.get('@type') in ['NewsArticle', 'Article']:
                    if item.get('headline'):
                        article['headline'] = item['headline']
                    if item.get('articleBody'):
                        article['body'] = item['articleBody']
                    if item.get('author'):
                        if isinstance(item['author'], dict):
                            article['author'] = item['author'].get('name', '')
                        else:
                            article['author'] = str(item['author'])
                    if item.get('datePublished'):
                        article['published_time'] = item['datePublished']
                    break
        elif isinstance(ld, dict) and ld.get('@type') in ['NewsArticle', 'Article']:
            if ld.get('headline'):
                article['headline'] = ld['headline']
            if ld.get('articleBody'):
                article['body'] = ld['articleBody']
    
    # Use bodyText if no body from JSON-LD
    if not article.get('body') and page_data.get('bodyText'):
        article['body'] = page_data['bodyText']
    
    # Clean up
    article = {k: v for k, v in article.items() if v}
    
    return article


def _extract_nba_news(page_data: dict) -> dict:
    """Extract NBA news listing from page data."""
    result = {
        'url': page_data.get('url', ''),
        'title': page_data.get('title', ''),
        'description': page_data.get('meta', {}).get('description', ''),
        'articles': []
    }
    
    # Extract article links
    seen_urls = set()
    for link in page_data.get('links', []):
        href = link.get('href', '')
        text = link.get('text', '').strip()
        
        # Filter for article links
        if href and text and '.html' in href and href not in seen_urls:
            seen_urls.add(href)
            result['articles'].append({
                'url': href,
                'title': text
            })
    
    # Limit to top articles
    result['articles'] = result['articles'][:20]
    
    return result


def _extract_players(page_data: dict) -> dict:
    """Extract NBA players listing from page data."""
    result = {
        'url': page_data.get('url', ''),
        'title': page_data.get('title', ''),
        'players': []
    }
    
    # Extract player links
    seen_urls = set()
    for link in page_data.get('links', []):
        href = link.get('href', '')
        text = link.get('text', '').strip()
        
        # Filter for player links
        if href and text and '/nba/players/' in href and href not in seen_urls:
            # Skip if it's the main players page URL
            if href.rstrip('/') == 'https://sports.yahoo.com/nba/players':
                continue
            seen_urls.add(href)
            result['players'].append({
                'url': href,
                'name': text
            })
    
    # Limit results
    result['players'] = result['players'][:50]
    
    return result


async def _get_article(url: str) -> dict:
    """Fetch and extract article data."""
    page_data = await _fetch_page_with_playwright(url)
    article = _extract_article_data(page_data)
    
    if not article.get('headline') and not article.get('description'):
        return {
            'success': False,
            'error': 'Could not extract article content',
            'url': url
        }
    
    return {
        'success': True,
        'article': article
    }


async def _get_nba_news() -> dict:
    """Fetch NBA news listing."""
    url = "https://sports.yahoo.com/nba/"
    page_data = await _fetch_page_with_playwright(url)
    news = _extract_nba_news(page_data)
    
    return {
        'success': True,
        'page': news
    }


async def _get_nba_players() -> dict:
    """Fetch NBA players listing."""
    url = "https://sports.yahoo.com/nba/players/"
    page_data = await _fetch_page_with_playwright(url)
    players = _extract_players(page_data)
    
    return {
        'success': True,
        'page': players
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Yahoo Sports access skill.
    
    Functions:
    - get_article: Extract article from a Yahoo Sports URL
    - get_nba_news: Get NBA news headlines from sports.yahoo.com/nba/
    - get_nba_players: Get NBA players listing from sports.yahoo.com/nba/players/
    """
    function = params.get('function', '')
    
    try:
        if function == 'get_article':
            url = params.get('url', '')
            if not url:
                return {'success': False, 'error': 'Missing required parameter: url'}
            
            if 'sports.yahoo.com' not in url:
                return {'success': False, 'error': 'URL must be from sports.yahoo.com'}
            
            return await _get_article(url)
        
        elif function == 'get_nba_news':
            return await _get_nba_news()
        
        elif function == 'get_nba_players':
            return await _get_nba_players()
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Available: get_article, get_nba_news, get_nba_players'
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Error executing {function}: {str(e)}'
        }