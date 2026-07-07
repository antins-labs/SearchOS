"""
Supreme Court Opinions Access Skill

Provides access to Supreme Court slip opinions and PDF documents.
Uses Playwright for browser automation due to Akamai bot protection.
"""

import asyncio
import tempfile
import os
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class SupremeCourtOpinionsClient:
    """Client for accessing Supreme Court opinions with browser automation."""
    
    BASE_URL = "https://www.supremecourt.gov"
    
    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        
    async def _ensure_browser(self):
        """Ensure browser is initialized."""
        if self._browser is None:
            playwright = await async_playwright().start()
            self._browser = await playwright.chromium.launch(headless=True)
            self._context = await self._browser.new_context(accept_downloads=True)
    
    async def close(self):
        """Close browser resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
    
    async def _create_page(self) -> Page:
        """Create a new page."""
        await self._ensure_browser()
        return await self._context.new_page()
    
    async def get_slip_opinions(self, term: str = "24") -> dict[str, Any]:
        """
        Get slip opinions for a given term.
        
        Args:
            term: Two-digit term year (e.g., "24" for 2024, "25" for 2025)
        
        Returns:
            Dict with success status, opinions list, and metadata
        """
        url = f"{self.BASE_URL}/opinions/slipopinion/{term}"
        
        try:
            page = await self._create_page()
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                title = await page.title()
                
                # Extract all opinion rows from tables
                opinions = []
                tables = await page.query_selector_all('table')
                
                for table in tables:
                    rows = await table.query_selector_all('tr')
                    
                    # Skip tables that don't look like opinion tables
                    if len(rows) < 2:
                        continue
                    
                    # Check if this is an opinion table
                    header_row = rows[0]
                    header_cells = await header_row.query_selector_all('td, th')
                    header_texts = [await c.inner_text() for c in header_cells]
                    
                    # Look for opinion table markers (columns like R-, Date, Docket, Name)
                    if not any(h in ''.join(header_texts) for h in ['R-', 'Docket', 'Name']):
                        continue
                    
                    # Parse opinion rows
                    for row in rows[1:]:
                        cells = await row.query_selector_all('td')
                        if not cells:
                            continue
                        
                        cell_texts = []
                        for cell in cells:
                            text = await cell.inner_text()
                            text = ' '.join(text.split())
                            cell_texts.append(text)
                        
                        # Get PDF link from the name column
                        pdf_link = await row.query_selector('a[href$=".pdf"]')
                        pdf_url = None
                        pdf_filename = None
                        
                        if pdf_link:
                            href = await pdf_link.get_attribute('href')
                            if href:
                                pdf_url = urljoin(self.BASE_URL, href)
                                pdf_filename = href.split('/')[-1]
                        
                        if len(cell_texts) >= 3:
                            opinion = {
                                'report_number': cell_texts[0] if len(cell_texts) > 0 else None,
                                'date': cell_texts[1] if len(cell_texts) > 1 else None,
                                'docket': cell_texts[2] if len(cell_texts) > 2 else None,
                                'case_name': cell_texts[3] if len(cell_texts) > 3 else None,
                                'justice': cell_texts[4] if len(cell_texts) > 4 else None,
                                'pdf_url': pdf_url,
                                'pdf_filename': pdf_filename,
                                'term': term,
                            }
                            
                            if opinion['case_name']:
                                opinions.append(opinion)
                
                return {
                    "success": True,
                    "term": term,
                    "url": url,
                    "title": title,
                    "total_opinions": len(opinions),
                    "opinions": opinions
                }
                
            finally:
                await page.close()
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "url": url,
                "term": term
            }
    
    async def get_relating_to_orders(self, term: str = "24") -> dict[str, Any]:
        """
        Get opinions relating to orders for a given term.
        
        Args:
            term: Two-digit term year
        
        Returns:
            Dict with success status, opinions list, and metadata
        """
        url = f"{self.BASE_URL}/opinions/relatingtoorders/{term}"
        
        try:
            page = await self._create_page()
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                title = await page.title()
                
                # Extract opinion rows - similar structure to slip opinions
                opinions = []
                tables = await page.query_selector_all('table')
                
                for table in tables:
                    rows = await table.query_selector_all('tr')
                    
                    if len(rows) < 2:
                        continue
                    
                    header_row = rows[0]
                    header_cells = await header_row.query_selector_all('td, th')
                    header_texts = [await c.inner_text() for c in header_cells]
                    
                    if not any(h in ''.join(header_texts) for h in ['R-', 'Docket', 'Name']):
                        continue
                    
                    for row in rows[1:]:
                        cells = await row.query_selector_all('td')
                        if not cells:
                            continue
                        
                        cell_texts = [' '.join((await c.inner_text()).split()) for c in cells]
                        
                        pdf_link = await row.query_selector('a[href$=".pdf"]')
                        pdf_url = None
                        pdf_filename = None
                        
                        if pdf_link:
                            href = await pdf_link.get_attribute('href')
                            if href:
                                pdf_url = urljoin(self.BASE_URL, href)
                                pdf_filename = href.split('/')[-1]
                        
                        if len(cell_texts) >= 3:
                            opinion = {
                                'report_number': cell_texts[0] if len(cell_texts) > 0 else None,
                                'date': cell_texts[1] if len(cell_texts) > 1 else None,
                                'docket': cell_texts[2] if len(cell_texts) > 2 else None,
                                'case_name': cell_texts[3] if len(cell_texts) > 3 else None,
                                'justice': cell_texts[4] if len(cell_texts) > 4 else None,
                                'pdf_url': pdf_url,
                                'pdf_filename': pdf_filename,
                                'term': term,
                            }
                            
                            if opinion['case_name']:
                                opinions.append(opinion)
                
                return {
                    "success": True,
                    "term": term,
                    "url": url,
                    "title": title,
                    "total_opinions": len(opinions),
                    "opinions": opinions
                }
                
            finally:
                await page.close()
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "url": url,
                "term": term
            }
    
    async def download_pdf(self, pdf_url: str) -> dict[str, Any]:
        """
        Download a Supreme Court opinion PDF.
        
        Args:
            pdf_url: Full URL to the PDF file or PDF filename
        
        Returns:
            Dict with success status, PDF data (base64), and metadata
        """
        import base64
        
        # Handle relative URLs or filenames
        if not pdf_url.startswith('http'):
            if pdf_url.endswith('.pdf'):
                # Assume it's a filename, construct URL
                pdf_url = f"{self.BASE_URL}/opinions/{pdf_url}"
            else:
                return {
                    "success": False,
                    "error": "Invalid PDF URL or filename",
                    "pdf_url": pdf_url
                }
        
        try:
            page = await self._create_page()
            
            try:
                # Navigate to the opinions page first to establish session
                term = self._extract_term_from_url(pdf_url)
                await page.goto(
                    f"{self.BASE_URL}/opinions/slipopinion/{term}",
                    wait_until="networkidle",
                    timeout=30000
                )
                
                # Find and click the PDF link
                pdf_link = await page.query_selector(f'a[href$="{pdf_url.split("/")[-1]}"]')
                
                if pdf_link:
                    # Download via click
                    async with page.expect_download() as download_info:
                        await pdf_link.click()
                    download = await download_info.value
                else:
                    return {
                        "success": False,
                        "error": f"PDF link not found on opinions page",
                        "pdf_url": pdf_url
                    }
                
                # Save to temp file
                temp_dir = tempfile.mkdtemp()
                pdf_path = os.path.join(temp_dir, download.suggested_filename)
                await download.save_as(pdf_path)
                
                # Read and encode
                with open(pdf_path, 'rb') as f:
                    pdf_bytes = f.read()
                
                # Clean up
                os.remove(pdf_path)
                os.rmdir(temp_dir)
                
                return {
                    "success": True,
                    "pdf_url": pdf_url,
                    "filename": download.suggested_filename,
                    "content_type": "application/pdf",
                    "size_bytes": len(pdf_bytes),
                    "data": base64.b64encode(pdf_bytes).decode('utf-8')
                }
                
            finally:
                await page.close()
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "pdf_url": pdf_url
            }
    
    def _extract_term_from_url(self, url: str) -> str:
        """Extract the term from a PDF URL."""
        # URLs are like: .../opinions/24pdf/filename.pdf
        match = re.search(r'/opinions/(\d{2})pdf/', url)
        if match:
            return match.group(1)
        return "24"  # Default
    
    async def search_opinions(self, query: str, term: Optional[str] = None) -> dict[str, Any]:
        """
        Search opinions by case name or docket number.
        
        Args:
            query: Search query (case name or docket number)
            term: Optional term to limit search (if None, searches recent terms)
        
        Returns:
            Dict with success status and matching opinions
        """
        query_lower = query.lower()
        matching_opinions = []
        terms_searched = []
        
        try:
            # Determine which terms to search
            if term:
                terms = [term]
            else:
                # Search recent terms
                terms = ['25', '24', '23', '22', '21']
            
            for t in terms:
                result = await self.get_slip_opinions(t)
                
                if result.get('success'):
                    terms_searched.append(t)
                    
                    for opinion in result.get('opinions', []):
                        # Search in case name and docket
                        case_name = (opinion.get('case_name') or '').lower()
                        docket = (opinion.get('docket') or '').lower()
                        
                        if query_lower in case_name or query_lower in docket:
                            matching_opinions.append(opinion)
            
            return {
                "success": True,
                "query": query,
                "terms_searched": terms_searched,
                "total_matches": len(matching_opinions),
                "matches": matching_opinions
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "query": query
            }


# Global client instance
_client: Optional[SupremeCourtOpinionsClient] = None


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Supreme Court opinions access functions.
    
    Functions:
        - get_slip_opinions: Get slip opinions for a term
        - get_relating_to_orders: Get opinions relating to orders
        - download_pdf: Download a PDF by URL
        - search_opinions: Search opinions by case name or docket
    
    Args:
        params: Dict containing 'function' and function-specific parameters
        ctx: Optional context (unused)
    
    Returns:
        Dict with success status and results or error details
    """
    global _client
    
    function = params.get('function')
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: 'function'",
            "available_functions": [
                "get_slip_opinions",
                "get_relating_to_orders", 
                "download_pdf",
                "search_opinions"
            ]
        }
    
    try:
        # Initialize client if needed
        if _client is None:
            _client = SupremeCourtOpinionsClient()
        
        if function == "get_slip_opinions":
            term = params.get("term", "24")
            return await _client.get_slip_opinions(term)
        
        elif function == "get_relating_to_orders":
            term = params.get("term", "24")
            return await _client.get_relating_to_orders(term)
        
        elif function == "download_pdf":
            pdf_url = params.get("pdf_url")
            if not pdf_url:
                return {
                    "success": False,
                    "error": "Missing required parameter: 'pdf_url'"
                }
            return await _client.download_pdf(pdf_url)
        
        elif function == "search_opinions":
            query = params.get("query")
            if not query:
                return {
                    "success": False,
                    "error": "Missing required parameter: 'query'"
                }
            term = params.get("term")
            return await _client.search_opinions(query, term)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}",
                "available_functions": [
                    "get_slip_opinions",
                    "get_relating_to_orders",
                    "download_pdf",
                    "search_opinions"
                ]
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


# For cleanup
async def cleanup():
    """Clean up browser resources."""
    global _client
    if _client:
        await _client.close()
        _client = None