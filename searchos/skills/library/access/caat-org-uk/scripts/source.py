"""
CAAT (Campaign Against Arms Trade) Company Data Access Skill

Fetches company data from caat.org.uk/data/companies/ pages.
Uses both the direct API (data.caat.org.uk) for structured data and
page scraping for description and additional links.
"""

import asyncio
import aiohttp
from typing import Any


async def fetch_api_data(session: aiohttp.ClientSession, slug: str) -> dict | None:
    """Fetch company data from the CAAT Data Hub API."""
    url = f"https://data.caat.org.uk/data-hub/api/summary/org/search/{slug}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception:
        pass
    return None


async def fetch_page_data(session: aiohttp.ClientSession, slug: str) -> dict | None:
    """Fetch company page HTML for description and links."""
    url = f"https://caat.org.uk/data/companies/{slug}/"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                html = await resp.text()
                return parse_page_html(html, url)
    except Exception:
        pass
    return None


def parse_page_html(html: str, base_url: str) -> dict:
    """Parse company page HTML for description and links."""
    from html.parser import HTMLParser
    
    class PageParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.description = ""
            self.breadcrumbs = []
            self.data_links = []
            self.in_article = False
            self.in_paragraph = False
            self.current_paragraph = ""
            self.in_breadcrumb = False
            self.breadcrumb_text = ""
            
        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            
            if tag == "article":
                self.in_article = True
            elif tag == "p" and self.in_article:
                self.in_paragraph = True
                self.current_paragraph = ""
            elif tag == "a":
                href = attrs_dict.get("href", "")
                if "/data/exports-uk" in href or href.endswith("/map") or "/arms-fairs" in href:
                    self.data_links.append({"url": href if href.startswith("http") else f"https://caat.org.uk{href}"})
                if "/data/companies" in href or "/data/countries" in href:
                    self.in_breadcrumb = True
                    self.breadcrumb_text = ""
                    
        def handle_endtag(self, tag):
            if tag == "article":
                self.in_article = False
            elif tag == "p" and self.in_paragraph:
                self.in_paragraph = False
                if self.current_paragraph.strip():
                    self.description = self.current_paragraph.strip()
            elif tag == "a":
                self.in_breadcrumb = False
                if self.breadcrumb_text.strip():
                    self.breadcrumbs.append(self.breadcrumb_text.strip())
                    
        def handle_data(self, data):
            if self.in_paragraph:
                self.current_paragraph += data
            elif self.in_breadcrumb:
                self.breadcrumb_text += data
    
    parser = PageParser()
    parser.feed(html)
    
    return {
        "description": parser.description,
        "breadcrumbs": parser.breadcrumbs,
        "data_links": parser.data_links
    }


async def get_company_data(slug: str) -> dict:
    """Get comprehensive company data from both API and page."""
    async with aiohttp.ClientSession() as session:
        # Fetch both API and page data concurrently
        api_task = fetch_api_data(session, slug)
        page_task = fetch_page_data(session, slug)
        
        api_data, page_data = await asyncio.gather(api_task, page_task)
        
        if not api_data and not page_data:
            return {
                "error": f"Company '{slug}' not found",
                "slug": slug
            }
        
        result = {
            "slug": slug,
            "source": "caat.org.uk"
        }
        
        # Add API data
        if api_data:
            result["company_name"] = api_data.get("name")
            result["id"] = api_data.get("id")
            result["address_count"] = api_data.get("addressCount")
            result["address_count_uk"] = api_data.get("addressCountUk")
            
            # Activities
            activities = api_data.get("activityList", [])
            result["activities"] = [a.get("name") for a in activities if a.get("name")]
            
            # Aliases
            aliases = api_data.get("aliasList", [])
            result["aliases"] = [{"name": a} if isinstance(a, str) else a for a in aliases]
            
            # SIPRI ranking
            sipri = api_data.get("sipriRank")
            if sipri:
                result["sipri_ranking"] = {
                    "rank": sipri.get("rank"),
                    "period": sipri.get("period"),
                    "value": sipri.get("value"),
                    "source": sipri.get("source")
                }
            
            # MoD procurement
            mod = api_data.get("modProcurement")
            if mod:
                result["mod_procurement"] = {
                    "rank": mod.get("rank"),
                    "period": mod.get("period"),
                    "value": mod.get("value"),
                    "source": mod.get("source")
                }
            
            # Arms fairs
            result["arms_fair_count"] = api_data.get("armsFairPastCount", 0)
            
            # Destination countries (concern)
            destinations = api_data.get("destinationConcernList", [])
            result["destination_countries"] = [
                {
                    "name": d.get("name"),
                    "slug": d.get("slug"),
                    "score": d.get("score")
                }
                for d in destinations
            ]
            
            result["destination_count"] = api_data.get("destinationCount", 0)
        
        # Add page data
        if page_data:
            if page_data.get("description") and not result.get("description"):
                result["description"] = page_data["description"]
            
            # Add data links
            if page_data.get("data_links"):
                result["data_links"] = page_data["data_links"]
        
        return result


async def search_companies(query: str, limit: int = 20) -> dict:
    """Search for companies (placeholder - would need to discover search API)."""
    # The search endpoint wasn't discovered in our probing
    # Return a helpful message
    return {
        "error": "Company search not yet implemented",
        "note": "Use get_company with the company slug from the URL, e.g., 'bae-systems', 'lockheed-martin'",
        "query": query
    }


async def get_company_by_name(name: str) -> dict:
    """Get company data by trying to convert name to slug."""
    # Convert company name to likely slug
    slug = name.lower().replace(" ", "-").replace("&", "and").replace(".", "")
    # Remove special characters
    slug = "".join(c for c in slug if c.isalnum() or c == "-")
    
    return await get_company_data(slug)


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute CAAT company data lookup.
    
    Functions:
    - get_company: Get detailed data for a specific company by slug
    - get_company_by_name: Get company data by name (auto-converts to slug)
    - search_companies: Search for companies (not yet implemented)
    """
    function = params.get("function", "")
    
    if function == "get_company":
        slug = params.get("slug", "").strip().strip("/")
        if not slug:
            return {"error": "Missing required parameter: slug"}
        return await get_company_data(slug)
    
    elif function == "get_company_by_name":
        name = params.get("name", "").strip()
        if not name:
            return {"error": "Missing required parameter: name"}
        return await get_company_by_name(name)
    
    elif function == "search_companies":
        query = params.get("query", "").strip()
        limit = params.get("limit", 20)
        return await search_companies(query, limit)
    
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": ["get_company", "get_company_by_name", "search_companies"]
        }


# For testing
if __name__ == "__main__":
    import json
    
    async def test():
        # Test get_company
        print("=== Testing get_company ===")
        result = await execute({"function": "get_company", "slug": "thyssenkrupp"})
        print(json.dumps(result, indent=2))
        
        print("\n=== Testing get_company_by_name ===")
        result = await execute({"function": "get_company_by_name", "name": "BAE Systems"})
        print(json.dumps(result, indent=2)[:1000])
    
    asyncio.run(test())