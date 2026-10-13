"""
Zhihu Zhuanlan (知乎专栏) Article Access Skill

This skill retrieves article content from Zhihu's Zhuanlan platform using Playwright
with stealth mode to bypass anti-scraping protections.

Note: Some articles may require login or CAPTCHA verification. This skill attempts
to access publicly available content using browser automation.
"""

import asyncio
import json
import re
from typing import Any, Dict, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class ZhihuZhuanlanClient:
    """Client for accessing Zhihu Zhuanlan articles with anti-scraping bypass"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Initialize browser and context if not already done"""
        if self._initialized:
            return
        
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )
        
        # Add stealth scripts to avoid detection
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            window.chrome = {
                runtime: {}
            };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
        """)
        
        # Visit homepage to establish session cookies
        page = await self.context.new_page()
        try:
            await page.goto("https://www.zhihu.com/", wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(2000)
        except Exception:
            pass
        finally:
            await page.close()
        
        self._initialized = True
    
    async def get_article(self, article_id: str) -> Dict[str, Any]:
        """
        Retrieve article data from Zhihu Zhuanlan
        
        Args:
            article_id: The article ID (from URL like /p/{article_id})
        
        Returns:
            Dictionary containing article data or error information
        """
        try:
            await self._ensure_initialized()
            
            page = await self.context.new_page()
            
            try:
                url = f"https://zhuanlan.zhihu.com/p/{article_id}"
                
                # Navigate to article
                await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                await page.wait_for_timeout(5000)
                
                # Check if we were redirected to login/CAPTCHA
                current_url = page.url
                if '/signin' in current_url or '/account/unhuman' in current_url or 'captcha' in current_url.lower():
                    return {
                        'success': False,
                        'error': 'access_blocked',
                        'message': 'Article requires login or CAPTCHA verification. Access blocked by Zhihu anti-scraping system.',
                        'article_id': article_id,
                        'redirect_url': current_url
                    }
                
                # Extract article data using multiple strategies
                article_data = await self._extract_article_data(page, article_id)
                
                if article_data and article_data.get('success'):
                    return article_data
                else:
                    # Check page title for more info
                    title = await page.title()
                    
                    return {
                        'success': False,
                        'error': 'article_not_found',
                        'message': f'Could not extract article data. Page title: {title}',
                        'article_id': article_id,
                        'page_title': title
                    }
                    
            finally:
                await page.close()
                
        except Exception as e:
            return {
                'success': False,
                'error': 'fetch_error',
                'message': str(e),
                'article_id': article_id
            }
    
    async def _extract_article_data(self, page: Page, article_id: str) -> Optional[Dict[str, Any]]:
        """Extract article data from loaded page"""
        
        # Strategy 1: Extract from window.INITIAL_STATE
        initial_state = await page.evaluate('() => window.INITIAL_STATE')
        
        if initial_state and isinstance(initial_state, dict):
            articles = initial_state.get('entities', {}).get('articles', {})
            if articles:
                # Get the first article
                article_key = list(articles.keys())[0]
                article = articles[article_key]
                
                return self._parse_article_from_state(article, article_id)
        
        # Strategy 2: Extract from script tags with JSON data
        script_data = await page.evaluate('''() => {
            const scripts = Array.from(document.querySelectorAll('script'));
            for (const script of scripts) {
                const text = script.textContent;
                if (text && text.includes('initialState')) {
                    try {
                        return JSON.parse(text);
                    } catch (e) {}
                }
            }
            return null;
        }''')
        
        if script_data and isinstance(script_data, dict) and 'initialState' in script_data:
            articles = script_data.get('initialState', {}).get('entities', {}).get('articles', {})
            if articles:
                article_key = list(articles.keys())[0]
                article = articles[article_key]
                
                return self._parse_article_from_state(article, article_id)
        
        # Strategy 3: Extract from DOM elements
        return await self._extract_from_dom(page, article_id)
    
    def _parse_article_from_state(self, article: Dict, article_id: str) -> Dict[str, Any]:
        """Parse article data from INITIAL_STATE"""
        author = article.get('author', {})
        
        return {
            'success': True,
            'article': {
                'id': article.get('id', article_id),
                'title': article.get('title', ''),
                'content': article.get('content', ''),
                'excerpt': article.get('excerpt', ''),
                'author': {
                    'id': author.get('id'),
                    'name': author.get('name'),
                    'url_token': author.get('urlToken'),
                    'avatar_url': author.get('avatarUrl'),
                    'headline': author.get('headline'),
                },
                'column': {
                    'id': article.get('column', {}).get('id'),
                    'name': article.get('column', {}).get('name'),
                } if article.get('column') else None,
                'created': article.get('created'),
                'updated': article.get('updated'),
                'comment_count': article.get('commentCount', 0),
                'voteup_count': article.get('voteupCount', 0),
                'url': f"https://zhuanlan.zhihu.com/p/{article_id}",
                'image_url': article.get('imageUrl'),
                'highlighted': article.get('highlighted', False),
                'topics': article.get('topics', []),
            }
        }
    
    async def _extract_from_dom(self, page: Page, article_id: str) -> Optional[Dict[str, Any]]:
        """Extract article data from DOM elements as fallback"""
        
        try:
            # Extract from meta tags first
            title_meta = await page.evaluate('''() => {
                const ogTitle = document.querySelector('meta[property="og:title"]');
                const twitterTitle = document.querySelector('meta[name="twitter:title"]');
                const titleTag = document.querySelector('title');
                return ogTitle?.content || twitterTitle?.content || titleTag?.text || '';
            }''')
            
            description_meta = await page.evaluate('''() => {
                const ogDesc = document.querySelector('meta[property="og:description"]');
                const twitterDesc = document.querySelector('meta[name="twitter:description"]');
                const metaDesc = document.querySelector('meta[name="description"]');
                return ogDesc?.content || twitterDesc?.content || metaDesc?.content || '';
            }''')
            
            # Try to get content
            content_elem = await page.query_selector('.Post-RichText, .RichText, article, [class*="RichText"]')
            content_text = await content_elem.inner_text() if content_elem else ''
            
            # Try to get author
            author_elem = await page.query_selector('.AuthorInfo-name, [class*="Author"] [class*="name"]')
            author_name = await author_elem.inner_text() if author_elem else ''
            
            # If we have meaningful data
            if title_meta or content_text:
                return {
                    'success': True,
                    'article': {
                        'id': article_id,
                        'title': title_meta.strip() if title_meta else '',
                        'content': content_text.strip(),
                        'excerpt': description_meta.strip() if description_meta else '',
                        'author': {
                            'name': author_name.strip() if author_name else '',
                        },
                        'url': f"https://zhuanlan.zhihu.com/p/{article_id}",
                    },
                    'extraction_method': 'dom'
                }
            
            return None
            
        except Exception as e:
            return None
    
    async def close(self):
        """Close browser and cleanup"""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.context = None
            self._initialized = False


# Global client instance
_client: Optional[ZhihuZhuanlanClient] = None


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute the Zhihu Zhuanlan skill
    
    Args:
        params: Dictionary with keys:
            - function: One of 'get_article', 'close'
            - article_id: Article ID for 'get_article' function (optional, can extract from URL)
            - url: Full article URL (alternative to article_id)
        ctx: Context object (unused)
    
    Returns:
        Dictionary with article data or error information
    """
    global _client
    
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'missing_function',
            'message': 'function parameter is required'
        }
    
    if function == 'close':
        if _client:
            await _client.close()
            _client = None
        return {'success': True, 'message': 'Client closed'}
    
    if function == 'get_article':
        # Get article_id from params
        article_id = params.get('article_id')
        
        # Or extract from URL
        if not article_id and params.get('url'):
            url = params['url']
            match = re.search(r'/p/(\d+)', url)
            if match:
                article_id = match.group(1)
        
        if not article_id:
            return {
                'success': False,
                'error': 'missing_article_id',
                'message': 'article_id or url (with /p/{id}) is required'
            }
        
        # Initialize client if needed
        if not _client:
            _client = ZhihuZhuanlanClient()
        
        # Get article
        result = await _client.get_article(article_id)
        return result
    
    return {
        'success': False,
        'error': 'invalid_function',
        'message': f'Unknown function: {function}'
    }