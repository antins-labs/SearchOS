"""
BJEEA (Beijing Education Examination Authority) Access Skill

This skill provides access to the Beijing Education Examination Authority website
(www.bjeea.cn), including:
- College admission score tables (高考高招录取投档线)
- Score distribution statistics (分数分布统计)
- Index pages with PDF/HTML document links
- General announcement pages

The website serves critical structured data for college admissions in Beijing.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup


class BJEEAClient:
    """Client for accessing BJEEA website content."""
    
    BASE_URL = "https://www.bjeea.cn"
    
    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
    
    async def fetch_page(self, url: str) -> Dict[str, Any]:
        """Fetch and parse a BJEEA page."""
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                resp = await client.get(url, headers=self.headers)
                resp.raise_for_status()
                
                # Handle encoding
                if not resp.encoding or resp.encoding == 'iso-8859-1':
                    resp.encoding = resp.apparent_encoding or 'utf-8'
                
                html = resp.text
                return self._parse_page(html, url)
                
            except httpx.TimeoutException:
                return {"error": "timeout", "message": f"Request timed out after {self.timeout}s"}
            except httpx.HTTPStatusError as e:
                return {"error": "http_error", "message": f"HTTP {e.response.status_code}", "status_code": e.response.status_code}
            except Exception as e:
                return {"error": "fetch_error", "message": str(e)}
    
    def _parse_page(self, html: str, url: str) -> Dict[str, Any]:
        """Parse HTML content and extract structured data."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract article metadata
        title = self._extract_title(soup)
        date = self._extract_date(soup)
        
        result = {
            "url": url,
            "title": title,
            "date": date,
            "success": True,
        }
        
        # Check for table data (score tables)
        tables = self._extract_tables(soup)
        if tables:
            result["type"] = "data_page"
            result["tables"] = tables
            result["table_count"] = len(tables)
            result["total_rows"] = sum(len(t.get("rows", [])) for t in tables)
        
        # Extract links (for index pages)
        links = self._extract_links(soup, url)
        if links:
            result["links"] = links
            result["link_count"] = len(links)
            result["type"] = "index_page" if "tables" not in result else "mixed_page"
        
        # Extract full text content
        content = self._extract_content(soup)
        if content:
            result["content"] = content
        
        return result
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article title."""
        # Try specific title class first
        title_elem = soup.select_one('.info-ctit')
        if title_elem:
            return title_elem.get_text(strip=True)
        
        # Try h1/h2 tags
        for tag in ['h1', 'h2']:
            elem = soup.find(tag)
            if elem:
                text = elem.get_text(strip=True)
                if text and '北京教育考试院' not in text and len(text) > 5:
                    return text
        
        # Try title tag
        title_tag = soup.find('title')
        if title_tag:
            text = title_tag.get_text(strip=True)
            # Clean up
            text = text.replace('北京教育考试院', '').strip()
            if text:
                return text
        
        return None
    
    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract article date."""
        # Try specific date class
        date_elem = soup.select_one('.info-item')
        if date_elem:
            text = date_elem.get_text(strip=True)
            match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
            if match:
                return match.group(1)
        
        # Try other date patterns
        date_elem = soup.select_one('.date, .time, .article-date')
        if date_elem:
            text = date_elem.get_text()
            match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)', text)
            if match:
                return match.group(1)
        
        # Search in HTML
        html = str(soup)
        match = re.search(r'(\d{4}-\d{2}-\d{2})', html)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_tables(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract all tables from the page."""
        tables = []
        
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            if not rows:
                continue
            
            # Extract headers
            header_row = rows[0]
            headers = []
            for cell in header_row.find_all(['th', 'td']):
                text = cell.get_text(strip=True)
                text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
                headers.append(text)
            
            # Extract data rows
            data_rows = []
            for row in rows[1:]:
                cells = []
                for cell in row.find_all('td'):
                    text = cell.get_text(strip=True)
                    text = re.sub(r'\s+', ' ', text)
                    cells.append(text)
                if cells:  # Only add non-empty rows
                    data_rows.append(cells)
            
            if headers and data_rows:
                tables.append({
                    "headers": headers,
                    "rows": data_rows,
                    "row_count": len(data_rows)
                })
        
        return tables
    
    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, str]]:
        """Extract relevant document links from index pages."""
        links = []
        seen_urls = set()
        
        # Find content area
        content = soup.select_one('.info-txt, .content, .view, #content')
        if not content:
            content = soup.find('body')
        
        if not content:
            return links
        
        for link in content.find_all('a', href=True):
            href = link.get('href', '').strip()
            text = link.get_text(strip=True)
            
            if not text or not href or len(text) < 3:
                continue
            
            # Resolve relative URLs
            if href.startswith('/'):
                href = urljoin(self.BASE_URL, href)
            elif not href.startswith('http'):
                href = urljoin(base_url, href)
            
            # Skip duplicates
            if href in seen_urls:
                continue
            seen_urls.add(href)
            
            # Filter relevant links (admission scores, statistics, etc.)
            keywords = ['统计', '分数', '录取', '分布', '投档', '批次', '高考', '招生', '高招']
            if any(kw in text for kw in keywords):
                links.append({
                    "text": text,
                    "url": href,
                    "type": self._classify_link(href)
                })
        
        return links
    
    def _classify_link(self, url: str) -> str:
        """Classify link type based on URL."""
        url_lower = url.lower()
        if url_lower.endswith('.pdf'):
            return "pdf"
        elif '.html' in url_lower:
            return "html"
        else:
            return "other"
    
    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract plain text content."""
        # Find content area
        content = soup.select_one('.info-txt, .content, .view, #content')
        if not content:
            content = soup.find('body')
        
        if not content:
            return None
        
        # Remove scripts and styles
        for tag in content.find_all(['script', 'style', 'nav', 'header', 'footer']):
            tag.decompose()
        
        text = content.get_text(separator='\n', strip=True)
        
        # Clean up
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n'.join(lines)
        
        # Limit length
        if len(text) > 10000:
            text = text[:10000] + "..."
        
        return text


async def fetch_announcement(url: str, max_rows: Optional[int] = None) -> Dict[str, Any]:
    """
    Fetch and parse a BJEEA announcement page.
    
    Args:
        url: URL of the announcement page
        max_rows: Maximum number of table rows to return (None for all)
    
    Returns:
        Dictionary with page data including tables and metadata
    """
    client = BJEEAClient()
    result = await client.fetch_page(url)
    
    if not result.get("success"):
        return result
    
    # Limit rows if requested
    if max_rows and "tables" in result:
        for table in result["tables"]:
            if "rows" in table:
                table["rows"] = table["rows"][:max_rows]
                table["row_count"] = len(table["rows"])
        result["total_rows"] = sum(len(t.get("rows", [])) for t in result["tables"])
    
    return result


async def search_admission_data(category: str = "gkgz", year: Optional[int] = None) -> Dict[str, Any]:
    """
    Search for admission-related announcements.
    
    Args:
        category: Announcement category (gkgz=高考高招, zkzz=中考中招)
        year: Year to filter by (optional)
    
    Returns:
        Dictionary with announcement list
    """
    # Common announcement list pages
    list_urls = {
        "gkgz": "https://www.bjeea.cn/html/gkgz/tzgg/",
        "zkzz": "https://www.bjeea.cn/html/zkzz/tzgg/",
    }
    
    url = list_urls.get(category)
    if not url:
        return {"error": "invalid_category", "message": f"Unknown category: {category}"}
    
    client = BJEEAClient()
    result = await client.fetch_page(url)
    
    if not result.get("success"):
        return result
    
    # Filter by year if specified
    if year and "links" in result:
        result["links"] = [
            link for link in result["links"]
            if str(year) in link.get("url", "") or str(year) in link.get("text", "")
        ]
    
    return result


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main execution function for the BJEEA access skill.
    
    Args:
        params: Dictionary with parameters:
            - function: "fetch_announcement" or "search_announcements"
            - For fetch_announcement:
                - url: (required) URL of the announcement page
                - max_rows: (optional) Maximum table rows to return
            - For search_announcements:
                - category: (optional) Category to search (default: gkgz)
                - year: (optional) Year to filter by
        ctx: Context (not used)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function")
    
    if not function:
        return {
            "error": "missing_function",
            "message": "Parameter 'function' is required. Use 'fetch_announcement' or 'search_announcements'"
        }
    
    if function == "fetch_announcement":
        url = params.get("url")
        if not url:
            return {"error": "missing_url", "message": "Parameter 'url' is required for fetch_announcement"}
        
        max_rows = params.get("max_rows")
        
        result = await fetch_announcement(url, max_rows)
        
        # Add summary
        if result.get("success"):
            summary = {
                "title": result.get("title"),
                "date": result.get("date"),
                "type": result.get("type"),
            }
            if "tables" in result:
                summary["tables"] = len(result["tables"])
                summary["total_rows"] = result.get("total_rows", 0)
            if "links" in result:
                summary["links"] = len(result["links"])
            
            result["summary"] = summary
        
        return result
    
    elif function == "search_announcements":
        category = params.get("category", "gkgz")
        year = params.get("year")
        
        result = await search_admission_data(category, year)
        
        # Add summary
        if result.get("success"):
            result["summary"] = {
                "category": category,
                "year": year,
                "link_count": len(result.get("links", []))
            }
        
        return result
    
    else:
        return {
            "error": "unknown_function",
            "message": f"Unknown function: {function}. Use 'fetch_announcement' or 'search_announcements'"
        }


# For testing
if __name__ == "__main__":
    async def test():
        # Test data page
        print("Testing data page (admission scores)...")
        result = await fetch_announcement(
            "https://www.bjeea.cn/html/gkgz/tzgg/2024/0720/85632.html",
            max_rows=5
        )
        print(f"Title: {result.get('title')}")
        print(f"Date: {result.get('date')}")
        print(f"Tables: {result.get('table_count')}")
        if result.get("tables"):
            print(f"Headers: {result['tables'][0]['headers']}")
            print(f"Sample row: {result['tables'][0]['rows'][0] if result['tables'][0]['rows'] else 'None'}")
        
        print("\n" + "="*80 + "\n")
        
        # Test index page
        print("Testing index page...")
        result = await fetch_announcement(
            "https://www.bjeea.cn/html/gkgz/tzgg/2025/0613/87140.html"
        )
        print(f"Title: {result.get('title')}")
        print(f"Date: {result.get('date')}")
        print(f"Links: {result.get('link_count')}")
        if result.get("links"):
            for link in result["links"][:3]:
                print(f"  - {link['text'][:50]} -> {link['type']}")
    
    asyncio.run(test())