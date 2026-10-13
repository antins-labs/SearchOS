"""
National Health Commission of China (NHC) Access Skill

This skill accesses the NHC website (www.nhc.gov.cn) to retrieve:
- Lists of medical institution announcements and official documents
- Detailed content of specific announcements
- Search results (if search is available)

The website uses aggressive anti-bot protection (Ray WAF or similar) that:
1. Returns 412 on first request
2. Serves a JavaScript challenge that sets HTTP-only cookies
3. Requires full browser JavaScript execution
4. May fail even with proper execution due to WAF fingerprinting

This implementation uses Playwright with stealth measures and extensive
retry logic to maximize success rate.
"""

import asyncio
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, parse_qs
from datetime import datetime


class NHCAccess:
    """Access client for NHC website with anti-bot bypass"""
    
    def __init__(self, timeout: int = 60, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = "https://www.nhc.gov.cn"
        
        # Common headers for requests
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }
        
        # Stealth JavaScript to inject
        self.stealth_js = """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
                configurable: true
            });
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const plugins = [
                        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
                        {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}
                    ];
                    plugins.length = 3;
                    return plugins;
                },
                configurable: true
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en-US', 'en'],
                configurable: true
            });
            
            Object.defineProperty(navigator, 'platform', {
                get: () => 'MacIntel',
                configurable: true
            });
            
            window.chrome = {
                runtime: {
                    connect: function() {},
                    sendMessage: function() {},
                    onMessage: { addListener: function() {} }
                },
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = function(parameters) {
                if (parameters.name === 'notifications') {
                    return Promise.resolve({ state: Notification.permission });
                }
                return originalQuery(parameters);
            };
            
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Intel Inc.';
                if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                return getParameter.apply(this, arguments);
            };
        """
    
    async def _retry_request(self, page, url: str) -> tuple:
        """
        Retry request with backoff, handling WAF challenge
        
        Returns:
            tuple: (success: bool, html: str)
        """
        for attempt in range(self.max_retries):
            try:
                response = await page.goto(
                    url,
                    wait_until="load",
                    timeout=self.timeout * 1000
                )
                
                if response.status == 200:
                    await asyncio.sleep(3)
                    html = await page.content()
                    if len(html) > 5000:
                        return True, html
                
                if response.status in (412, 400):
                    wait_time = 10 + (attempt * 5)
                    await asyncio.sleep(wait_time)
                    
                    response = await page.reload(wait_until="load", timeout=self.timeout * 1000)
                    await asyncio.sleep(5)
                    
                    html = await page.content()
                    if response.status == 200 and len(html) > 5000:
                        return True, html
                
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(5 * (2 ** attempt))
                    
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(5 * (2 ** attempt))
        
        return False, ""
    
    async def _create_browser_context(self, playwright):
        """Create browser context with stealth settings"""
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X_10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            java_script_enabled=True,
            extra_http_headers=self.headers
        )
        
        await context.add_init_script(self.stealth_js)
        
        return browser, context
    
    async def get_list(self, url: str, page: int = 1, max_items: int = 50) -> dict:
        """Get list of documents from a category page"""
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser, context = await self._create_browser_context(p)
            page_obj = await context.new_page()
            
            try:
                if page > 1:
                    if "list.shtml" in url and "list_" not in url:
                        url = url.replace("list.shtml", f"list_{page}.shtml")
                    elif "?" not in url:
                        url = f"{url}?page={page}"
                    else:
                        url = f"{url}&page={page}"
                
                success, html = await self._retry_request(page_obj, url)
                
                if not success:
                    return {
                        "success": False,
                        "error": "Failed to bypass anti-bot protection after multiple retries",
                        "error_code": "WAF_BLOCKED",
                        "url": url,
                        "items": [],
                        "total": 0
                    }
                
                title = await page_obj.title()
                
                items = await page_obj.evaluate("""() => {
                    const items = [];
                    const selectors = ['ul li a', '.list li a', '.news-list li a', '.content-list li a', 'a[href$=".shtml"]'];
                    
                    let links = [];
                    for (const selector of selectors) {
                        const found = document.querySelectorAll(selector);
                        if (found.length > links.length) {
                            links = Array.from(found);
                        }
                    }
                    
                    links.forEach(link => {
                        const text = link.textContent.trim();
                        const href = link.getAttribute('href');
                        
                        if (text.length > 5 && href && (href.includes('.shtml') || href.includes('list'))) {
                            let date = '';
                            const parent = link.closest('li');
                            if (parent) {
                                const dateEl = parent.querySelector('.date, .time, span');
                                if (dateEl) {
                                    date = dateEl.textContent.trim();
                                }
                            }
                            
                            items.push({
                                title: text.substring(0, 200),
                                url: href.startsWith('http') ? href : (window.location.origin + href),
                                date: date
                            });
                        }
                    });
                    
                    return items.slice(0, 100);
                }""")
                
                pagination = await page_obj.evaluate("""() => {
                    const pageLinks = document.querySelectorAll('a, span, li');
                    const pages = [];
                    
                    pageLinks.forEach(el => {
                        const text = el.textContent.trim();
                        if (/^\\d+$/.test(text)) {
                            pages.push(parseInt(text));
                        }
                    });
                    
                    return {
                        pages: [...new Set(pages)].sort((a, b) => a - b),
                        has_next: !!document.querySelector('a:contains("下一页"), a.next, a[href*="page"]')
                    };
                }""")
                
                return {
                    "success": True,
                    "url": url,
                    "title": title,
                    "items": items[:max_items],
                    "total": len(items),
                    "page": page,
                    "pagination": pagination,
                    "accessed_at": datetime.now().isoformat()
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "error_code": "REQUEST_FAILED",
                    "url": url,
                    "items": [],
                    "total": 0
                }
            finally:
                await browser.close()
    
    async def get_detail(self, url: str) -> dict:
        """Get full content of a document"""
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser, context = await self._create_browser_context(p)
            page = await context.new_page()
            
            try:
                success, html = await self._retry_request(page, url)
                
                if not success:
                    return {
                        "success": False,
                        "error": "Failed to bypass anti-bot protection",
                        "error_code": "WAF_BLOCKED",
                        "url": url
                    }
                
                content = await page.evaluate("""() => {
                    const selectors = ['.pages_content', '#content', '.content', '.xwcon', 'article', '.con', '.article-content', '.text-content'];
                    
                    let contentEl = null;
                    for (const selector of selectors) {
                        contentEl = document.querySelector(selector);
                        if (contentEl) break;
                    }
                    
                    if (!contentEl) {
                        contentEl = document.body;
                    }
                    
                    const titleEl = document.querySelector('h1, .title, .article-title, .item-title');
                    const title = titleEl ? titleEl.textContent.trim() : document.title;
                    
                    const dateEl = document.querySelector('.date, .time, [class*="date"]');
                    const date = dateEl ? dateEl.textContent.trim() : '';
                    
                    const sourceEl = document.querySelector('.source, .laiyuan, [class*="source"]');
                    const source = sourceEl ? sourceEl.textContent.trim() : '';
                    
                    const authorEl = document.querySelector('.author, .zuozhe, [class*="author"]');
                    const author = authorEl ? authorEl.textContent.trim() : '';
                    
                    const content = contentEl.textContent.replace(/\\s+/g, ' ').trim();
                    const contentHtml = contentEl.innerHTML;
                    
                    return {
                        title: title,
                        content: content,
                        content_html: contentHtml,
                        date: date,
                        source: source,
                        author: author,
                        url: window.location.href
                    };
                }""")
                
                content["success"] = True
                content["url"] = url
                content["accessed_at"] = datetime.now().isoformat()
                content["content_length"] = len(content.get("content", ""))
                
                return content
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "error_code": "REQUEST_FAILED",
                    "url": url
                }
            finally:
                await browser.close()
    
    async def search(self, keyword: str, category: Optional[str] = None, max_items: int = 20) -> dict:
        """Search for documents (if available)"""
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser, context = await self._create_browser_context(p)
            page = await context.new_page()
            
            try:
                search_urls = [
                    f"{self.base_url}/search.shtml?keyword={keyword}",
                    f"{self.base_url}/s?wd={keyword}",
                    f"{self.base_url}/search?keyword={keyword}",
                ]
                
                if category:
                    search_urls = [f"{url}&category={category}" for url in search_urls]
                
                for search_url in search_urls:
                    try:
                        success, html = await self._retry_request(page, search_url)
                        
                        if success and len(html) > 5000:
                            results = await page.evaluate("""() => {
                                const items = [];
                                const links = document.querySelectorAll('a');
                                
                                links.forEach(link => {
                                    const text = link.textContent.trim();
                                    const href = link.getAttribute('href');
                                    
                                    if (text.length > 10 && href && href.includes('.shtml')) {
                                        items.push({
                                            title: text.substring(0, 200),
                                            url: href.startsWith('http') ? href : (window.location.origin + href)
                                        });
                                    }
                                });
                                
                                return items;
                            }""")
                            
                            if results:
                                return {
                                    "success": True,
                                    "keyword": keyword,
                                    "category": category,
                                    "results": results[:max_items],
                                    "total": len(results),
                                    "search_url": search_url,
                                    "accessed_at": datetime.now().isoformat()
                                }
                    except:
                        continue
                
                return {
                    "success": False,
                    "error": "Search functionality not available or blocked",
                    "error_code": "NO_SEARCH",
                    "keyword": keyword,
                    "results": [],
                    "total": 0
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "error_code": "REQUEST_FAILED",
                    "keyword": keyword,
                    "results": [],
                    "total": 0
                }
            finally:
                await browser.close()


async def execute(params: dict, ctx: Any = None) -> dict:
    """
    Main entry point for NHC access skill
    
    Args:
        params: Function parameters including 'function' name
        ctx: Optional context
    
    Returns:
        dict with results
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "error_code": "MISSING_FUNCTION"
        }
    
    timeout = params.get("timeout", 60)
    max_retries = params.get("max_retries", 3)
    client = NHCAccess(timeout=timeout, max_retries=max_retries)
    
    try:
        if function == "get_list":
            url = params.get("url")
            if not url:
                return {
                    "success": False,
                    "error": "Missing required parameter: url",
                    "error_code": "MISSING_URL"
                }
            
            page = params.get("page", 1)
            max_items = params.get("max_items", 50)
            
            return await client.get_list(url, page, max_items)
        
        elif function == "get_detail":
            url = params.get("url")
            if not url:
                return {
                    "success": False,
                    "error": "Missing required parameter: url",
                    "error_code": "MISSING_URL"
                }
            
            return await client.get_detail(url)
        
        elif function == "search":
            keyword = params.get("keyword")
            if not keyword:
                return {
                    "success": False,
                    "error": "Missing required parameter: keyword",
                    "error_code": "MISSING_KEYWORD"
                }
            
            category = params.get("category")
            max_items = params.get("max_items", 20)
            
            return await client.search(keyword, category, max_items)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}",
                "error_code": "UNKNOWN_FUNCTION",
                "available_functions": ["get_list", "get_detail", "search"]
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_code": "EXECUTION_ERROR"
        }