"""
The Guardian article extractor skill for SearchOS.
Extracts article content, metadata, and publication info from The Guardian news articles.
"""

import json
import re
from typing import Any
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright


async def extract_article(url: str) -> dict[str, Any]:
    """
    Extract article content and metadata from a Guardian URL.
    
    Args:
        url: The Guardian article URL
        
    Returns:
        Dictionary with article data or error information
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                viewport={'width': 1280, 'height': 720}
            )
            page = await context.new_page()
            
            # Navigate to the article
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            # Get page content
            html = await page.content()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Check if it's a valid article page
            title_tag = soup.find('title')
            if title_tag and 'Page Not Found' in title_tag.get_text():
                return {
                    'error': 'Article not found',
                    'error_code': 'NOT_FOUND',
                    'url': url
                }
            
            # Initialize result
            result = {
                'url': url,
                'headline': None,
                'description': None,
                'authors': [],
                'section': None,
                'tags': [],
                'published_date': None,
                'modified_date': None,
                'article_text': None,
                'word_count': 0,
                'publication': 'The Guardian'
            }
            
            # Extract from LD+JSON (most reliable)
            ld_json_scripts = soup.find_all('script', type='application/ld+json')
            for script in ld_json_scripts:
                try:
                    data = json.loads(script.string)
                    
                    # Handle list format
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get('@type') == 'NewsArticle':
                                result['headline'] = item.get('headline')
                                result['published_date'] = item.get('datePublished')
                                result['modified_date'] = item.get('dateModified')
                                
                                authors = item.get('author', [])
                                if isinstance(authors, list):
                                    result['authors'] = [
                                        a.get('name', a) if isinstance(a, dict) else a 
                                        for a in authors
                                    ]
                                
                                article_body = item.get('articleBody', '')
                                if article_body:
                                    result['article_text'] = article_body
                                    result['word_count'] = len(article_body.split())
                                break
                    
                    # Handle dict format
                    elif isinstance(data, dict) and data.get('@type') == 'NewsArticle':
                        result['headline'] = data.get('headline')
                        result['published_date'] = data.get('datePublished')
                        result['modified_date'] = data.get('dateModified')
                        
                        authors = data.get('author', [])
                        if isinstance(authors, list):
                            result['authors'] = [
                                a.get('name', a) if isinstance(a, dict) else a 
                                for a in authors
                            ]
                        
                        article_body = data.get('articleBody', '')
                        if article_body:
                            result['article_text'] = article_body
                            result['word_count'] = len(article_body.split())
                            
                except (json.JSONDecodeError, AttributeError):
                    continue
            
            # Extract from meta tags (supplement or fallback)
            meta_mappings = {
                'description': ['description', 'og:description'],
                'section': ['article:section'],
                'published_date': ['article:published_time'],
                'modified_date': ['article:modified_time'],
            }
            
            for field, meta_names in meta_mappings.items():
                if not result.get(field):
                    for meta_name in meta_names:
                        meta = soup.find('meta', attrs={'property': meta_name}) or \
                               soup.find('meta', attrs={'name': meta_name})
                        if meta and meta.get('content'):
                            result[field] = meta.get('content')
                            break
            
            # Extract author from meta if not in LD+JSON
            if not result['authors']:
                author_meta = soup.find('meta', attrs={'property': 'article:author'}) or \
                             soup.find('meta', attrs={'name': 'article:author'})
                if author_meta and author_meta.get('content'):
                    result['authors'] = [author_meta.get('content')]
            
            # Extract tags
            tags_meta = soup.find('meta', attrs={'name': 'article:tag'}) or \
                       soup.find('meta', attrs={'property': 'article:tag'})
            if tags_meta and tags_meta.get('content'):
                result['tags'] = [t.strip() for t in tags_meta.get('content').split(',')]
            
            # Extract article text from HTML if not in LD+JSON
            if not result['article_text']:
                article = soup.find('article')
                if article:
                    paragraphs = article.find_all('p')
                    texts = []
                    for p in paragraphs:
                        text = p.get_text().strip()
                        # Filter out non-content paragraphs (social buttons, etc.)
                        if text and len(text) > 20 and not any(skip in text.lower() for skip in ['sign up', 'subscribe', 'follow us', 'share on']):
                            texts.append(text)
                    
                    if texts:
                        result['article_text'] = '\n\n'.join(texts)
                        result['word_count'] = sum(len(t.split()) for t in texts)
            
            return result
            
        except Exception as e:
            return {
                'error': str(e),
                'error_code': 'EXTRACTION_ERROR',
                'url': url
            }
        finally:
            await browser.close()


async def get_sections() -> dict[str, Any]:
    """
    Get a list of main sections from The Guardian.
    
    Returns:
        Dictionary with section information
    """
    # Common Guardian sections (static list for reliability)
    sections = [
        {'id': 'world', 'name': 'World news'},
        {'id': 'uk-news', 'name': 'UK news'},
        {'id': 'politics', 'name': 'Politics'},
        {'id': 'environment', 'name': 'Environment'},
        {'id': 'science', 'name': 'Science'},
        {'id': 'global', 'name': 'Global'},
        {'id': 'football', 'name': 'Football'},
        {'id': 'culture', 'name': 'Culture'},
        {'id': 'business', 'name': 'Business'},
        {'id': 'technology', 'name': 'Technology'},
        {'id': 'film', 'name': 'Film'},
        {'id': 'music', 'name': 'Music'},
        {'id': 'tv-and-radio', 'name': 'TV & radio'},
        {'id': 'books', 'name': 'Books'},
        {'id': 'artanddesign', 'name': 'Art and design'},
        {'id': 'stage', 'name': 'Stage'},
        {'id': 'games', 'name': 'Games'},
        {'id': 'education', 'name': 'Education'},
        {'id': 'society', 'name': 'Society'},
        {'id': 'law', 'name': 'Law'},
        {'id': 'us-news', 'name': 'US news'},
        {'id': 'australia-news', 'name': 'Australia news'},
        {'id': 'europe-news', 'name': 'Europe news'},
        {'id': 'asia', 'name': 'Asia'},
        {'id': 'americas', 'name': 'Americas'},
        {'id': 'middleeast', 'name': 'Middle East'},
        {'id': 'africa', 'name': 'Africa'},
        {'id': 'cities', 'name': 'Cities'},
        {'id': 'development', 'name': 'Global development'},
        {'id': 'inequality', 'name': 'Inequality'},
        {'id': 'opinion', 'name': 'Opinion'},
        {'id': 'sport', 'name': 'Sport'},
        {'id': 'lifestyle', 'name': 'Lifestyle'},
        {'id': 'health', 'name': 'Health'},
        {'id': 'money', 'name': 'Money'},
        {'id': 'travel', 'name': 'Travel'},
        {'id': 'fashion', 'name': 'Fashion'},
    ]
    
    return {
        'sections': sections,
        'total': len(sections)
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for The Guardian skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ('extract_article', 'get_sections')
            - Additional parameters depending on function

        
    Returns:
        Dictionary with results or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'error': 'Missing required parameter: function',
            'error_code': 'MISSING_PARAMETER'
        }
    
    if function == 'extract_article':
        url = params.get('url')
        if not url:
            return {
                'error': 'Missing required parameter: url',
                'error_code': 'MISSING_PARAMETER'
            }
        
        # Validate URL
        if not url.startswith('https://www.theguardian.com/'):
            return {
                'error': 'URL must be from www.theguardian.com',
                'error_code': 'INVALID_URL'
            }
        
        return await extract_article(url)
    
    elif function == 'get_sections':
        return await get_sections()
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'error_code': 'UNKNOWN_FUNCTION',
            'available_functions': ['extract_article', 'get_sections']
        }