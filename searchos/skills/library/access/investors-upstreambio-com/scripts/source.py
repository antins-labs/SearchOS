"""
SearchOS Access Skill for investors.upstreambio.com
Extracts SEC filing data from Upstream Bio investor relations site.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright, Browser, Page, BrowserContext


class UpstreamBioSECExtractor:
    """Extracts SEC filing data from investors.upstreambio.com"""
    
    BASE_URL = "https://investors.upstreambio.com"
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
    
    async def _init_browser(self):
        """Initialize browser with stealth configuration"""
        if self.browser is None:
            p = await async_playwright().start()
            self.browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=site-per-process',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            self._playwright = p
    
    async def _create_context(self) -> BrowserContext:
        """Create a browser context with stealth settings"""
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
        )
        
        # Stealth scripts
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            window.chrome = {runtime: {}};
        """)
        
        return context
    
    async def _load_page(self, url: str, retries: int = 3) -> Optional[str]:
        """Load page with retries and Cloudflare bypass"""
        await self._init_browser()
        
        for attempt in range(retries):
            context = None
            page = None
            try:
                context = await self._create_context()
                page = await context.new_page()
                
                # Navigate with extended timeout
                await page.goto(url, wait_until='domcontentloaded', timeout=90000)
                
                # Wait for potential Cloudflare challenge
                await page.wait_for_timeout(10000)
                
                # Check if we got past Cloudflare
                title = await page.title()
                html = await page.content()
                
                # Check for blocking
                if 'Access Denied' in html or len(html) < 10000:
                    raise Exception("Blocked or insufficient content")
                
                # Store for cleanup
                self._page = page
                self._context = context
                
                return html
                
            except Exception as e:
                if page:
                    await page.close()
                if context:
                    await context.close()
                
                if attempt == retries - 1:
                    raise e
                
                # Wait before retry
                await asyncio.sleep(5)
        
        return None
    
    async def list_sec_filings(
        self,
        filing_type: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        List SEC filings from the investor relations page.
        
        Args:
            filing_type: Optional filter by filing type (e.g., 'S-1', '10-K', '8-K')
            limit: Optional limit on number of results
            
        Returns:
            Dict with filings list and metadata
        """
        url = f"{self.BASE_URL}/financial-information/sec-filings"
        
        try:
            html = await self._load_page(url)
            
            if not html:
                return {
                    "error": "Failed to load page",
                    "filings": [],
                    "total": 0
                }
            
            # Extract filings data using JavaScript
            filings_data = await self._page.evaluate('''() => {
                const results = {
                    filings: [],
                    page_title: document.title,
                    page_url: window.location.href
                };
                
                // Find the filings table
                const table = document.querySelector('table');
                if (!table) return results;
                
                const headers = [];
                const rows = table.querySelectorAll('tr');
                
                rows.forEach((row, idx) => {
                    const cells = row.querySelectorAll('th, td');
                    
                    if (idx === 0 || row.querySelector('th')) {
                        // Extract headers
                        cells.forEach(cell => {
                            headers.push(cell.textContent.trim());
                        });
                    } else {
                        // Extract data row
                        const rowData = {};
                        cells.forEach((cell, cellIdx) => {
                            const header = headers[cellIdx] || `field_${cellIdx}`;
                            const link = cell.querySelector('a');
                            
                            if (link) {
                                rowData[header] = {
                                    text: cell.textContent.trim(),
                                    href: link.href
                                };
                            } else {
                                rowData[header] = cell.textContent.trim();
                            }
                        });
                        
                        if (Object.keys(rowData).length > 0) {
                            results.filings.push(rowData);
                        }
                    }
                });
                
                return results;
            }''')
            
            filings = filings_data.get('filings', [])
            
            # Filter by filing type if specified
            if filing_type:
                filing_type_lower = filing_type.lower()
                filings = [
                    f for f in filings
                    if any(
                        filing_type_lower in str(v).lower()
                        for v in f.values()
                    )
                ]
            
            # Apply limit
            if limit:
                filings = filings[:limit]
            
            return {
                "error": None,
                "filings": filings,
                "total": len(filings),
                "page_url": filings_data.get('page_url'),
                "page_title": filings_data.get('page_title')
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "filings": [],
                "total": 0
            }
        finally:
            await self._cleanup()
    
    async def get_sec_filing_detail(
        self,
        filing_type: str,
        accession_number: str
    ) -> Dict[str, Any]:
        """
        Get details of a specific SEC filing.
        
        Args:
            filing_type: Filing type (e.g., 's-1a', '10-k')
            accession_number: SEC accession number (e.g., '0001193125-24-233296')
            
        Returns:
            Dict with filing details and documents
        """
        # Normalize filing type
        filing_type_norm = filing_type.lower().replace('-', '').replace(' ', '-')
        url = f"{self.BASE_URL}/sec-filings/sec-filing/{filing_type_norm}/{accession_number}/"
        
        try:
            html = await self._load_page(url)
            
            if not html:
                return {
                    "error": "Failed to load filing detail page",
                    "filing_type": filing_type,
                    "accession_number": accession_number
                }
            
            # Extract filing details
            detail_data = await self._page.evaluate('''() => {
                const result = {
                    page_title: document.title,
                    page_url: window.location.href,
                    documents: [],
                    filing_info: {}
                };
                
                // Extract document links
                document.querySelectorAll('a').forEach(a => {
                    const href = a.href;
                    const text = a.textContent.trim();
                    
                    // Look for document links (PDFs, HTML, etc.)
                    if (href && (
                        href.includes('.pdf') ||
                        href.includes('.htm') ||
                        href.includes('.html') ||
                        href.includes('sec.gov') ||
                        href.includes('edgar')
                    )) {
                        result.documents.push({
                            text: text,
                            href: href
                        });
                    }
                });
                
                // Try to extract filing info from page content
                const body = document.body.innerText;
                
                // Extract common fields
                const patterns = {
                    'form_type': /Form[:\s]+([A-Z0-9-]+)/i,
                    'file_number': /File[:\s]+([0-9-]+)/i,
                    'filed_date': /Filed[:\s]+([A-Za-z0-9, ]+)/i,
                    'accepted_date': /Accepted[:\s]+([A-Za-z0-9, :]+)/i,
                };
                
                for (const [key, pattern] of Object.entries(patterns)) {
                    const match = body.match(pattern);
                    if (match) {
                        result.filing_info[key] = match[1].trim();
                    }
                }
                
                return result;
            }''')
            
            return {
                "error": None,
                "filing_type": filing_type,
                "accession_number": accession_number,
                "page_url": detail_data.get('page_url'),
                "page_title": detail_data.get('page_title'),
                "documents": detail_data.get('documents', []),
                "filing_info": detail_data.get('filing_info', {})
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "filing_type": filing_type,
                "accession_number": accession_number
            }
        finally:
            await self._cleanup()
    
    async def search_filings(
        self,
        query: str,
        limit: Optional[int] = 10
    ) -> Dict[str, Any]:
        """
        Search SEC filings by query.
        
        Args:
            query: Search term (searches in filing metadata)
            limit: Maximum results to return
            
        Returns:
            Dict with matching filings
        """
        # Get all filings first
        result = await self.list_sec_filings()
        
        if result.get('error'):
            return result
        
        filings = result.get('filings', [])
        query_lower = query.lower()
        
        # Filter filings by query
        matching = []
        for filing in filings:
            # Search in all text fields
            searchable = ' '.join(
                str(v.get('text', v) if isinstance(v, dict) else v)
                for v in filing.values()
            ).lower()
            
            if query_lower in searchable:
                matching.append(filing)
        
        if limit:
            matching = matching[:limit]
        
        return {
            "error": None,
            "query": query,
            "filings": matching,
            "total": len(matching)
        }
    
    async def _cleanup(self):
        """Clean up browser resources"""
        try:
            if hasattr(self, '_page') and self._page:
                await self._page.close()
            if hasattr(self, '_context') and self._context:
                await self._context.close()
        except:
            pass
    
    async def close(self):
        """Close the browser"""
        await self._cleanup()
        if self.browser:
            await self.browser.close()
            self.browser = None
        if hasattr(self, '_playwright'):
            await self._playwright.stop()


# Global extractor instance
_extractor: Optional[UpstreamBioSECExtractor] = None


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute SEC filing extraction from investors.upstreambio.com
    
    Args:
        params: Dict with:
            - function: One of 'list_sec_filings', 'get_sec_filing_detail', 'search_filings'
            - Additional parameters depending on function
            
        ctx: Context (unused)
        
    Returns:
        Dict with results or error
    """
    global _extractor
    
    function = params.get('function')
    if not function:
        return {
            "error": "Missing required parameter: function",
            "valid_functions": ['list_sec_filings', 'get_sec_filing_detail', 'search_filings']
        }
    
    # Create extractor if needed
    if _extractor is None:
        _extractor = UpstreamBioSECExtractor()
    
    try:
        if function == 'list_sec_filings':
            filing_type = params.get('filing_type')
            limit = params.get('limit')
            
            result = await _extractor.list_sec_filings(
                filing_type=filing_type,
                limit=limit
            )
            
        elif function == 'get_sec_filing_detail':
            filing_type = params.get('filing_type')
            accession_number = params.get('accession_number')
            
            if not filing_type or not accession_number:
                return {
                    "error": "Missing required parameters: filing_type and accession_number",
                    "example": {
                        "filing_type": "s-1a",
                        "accession_number": "0001193125-24-233296"
                    }
                }
            
            result = await _extractor.get_sec_filing_detail(
                filing_type=filing_type,
                accession_number=accession_number
            )
            
        elif function == 'search_filings':
            query = params.get('query')
            limit = params.get('limit', 10)
            
            if not query:
                return {
                    "error": "Missing required parameter: query"
                }
            
            result = await _extractor.search_filings(
                query=query,
                limit=limit
            )
            
        else:
            return {
                "error": f"Unknown function: {function}",
                "valid_functions": ['list_sec_filings', 'get_sec_filing_detail', 'search_filings']
            }
        
        return result
        
    except Exception as e:
        return {
            "error": f"Execution failed: {str(e)}",
            "function": function
        }
    finally:
        # Clean up after each request
        if _extractor:
            await _extractor._cleanup()


# For testing
if __name__ == "__main__":
    async def test():
        print("=== Testing list_sec_filings ===")
        result = await execute({"function": "list_sec_filings", "limit": 5})
        print(json.dumps(result, indent=2))
        
        if result.get('filings'):
            print("\n=== Sample filing ===")
            print(json.dumps(result['filings'][0], indent=2))
    
    asyncio.run(test())