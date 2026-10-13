"""
IDEA Special Voting Arrangements (SVA) Data Access Skill

This skill extracts structured data from International IDEA's Special Voting Arrangements
database, including global data on postal voting, early voting, proxy voting, mobile voting,
and case decisions. The data is presented through Google Data Studio visualizations embedded
in Drupal pages.

Key pages:
- Overview: https://www.idea.int/data-tools/tools/special-voting-arrangements
- Postal voting (in-country): https://www.idea.int/data-tools/tools/special-voting-arrangements/postal-in-country
- Early voting: https://www.idea.int/data-tools/tools/special-voting-arrangements/early-voting
- Proxy voting (in-country): https://www.idea.int/data-tools/tools/special-voting-arrangements/proxy-voting-in-country
- Mobile voting: https://www.idea.int/data-tools/tools/special-voting-arrangements/mobile-voting
- Data Explorer: https://www.idea.int/data-tools/tools/special-voting-arrangements/data-explorer
- Case Decisions: https://www.idea.int/data-tools/tools/special-voting-arrangements/case-decision-database
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin
import re


# Base URL for IDEA SVA data
BASE_URL = "https://www.idea.int/data-tools/tools/special-voting-arrangements"

# SVA types and their page paths
SVA_PAGES = {
    "overview": "",
    "postal_in_country": "/postal-in-country",
    "early_voting": "/early-voting",
    "proxy_voting": "/proxy-voting-in-country",
    "mobile_voting": "/mobile-voting",
    "data_explorer": "/data-explorer",
    "case_decisions": "/case-decision-database",
}

# Google Data Studio embed URLs for each SVA type
DATASTUDIO_EMBEDS = {
    "postal_in_country": {
        "map": "https://datastudio.google.com/embed/reporting/dd036d43-94e6-43be-9f53-a1c5bfdc014e/page/LnVAC",
        "table": "https://datastudio.google.com/embed/reporting/2141ee71-0bb2-4f5c-a5d6-39f2a98416fc/page/LnVAC",
    },
    "early_voting": {
        "map": "https://datastudio.google.com/embed/reporting/2eccc5dd-773d-43fd-9380-1c4b75df440e/page/LnVAC",
        "table": "https://datastudio.google.com/embed/reporting/6a15fd41-e225-4298-8b00-dcb3ab09f9b1/page/LnVAC",
    },
    "proxy_voting": {
        "map": "https://datastudio.google.com/embed/reporting/7547b3a6-8e8b-44ac-a7c8-68ec3a556ad4/page/LnVAC",
        "table": "https://datastudio.google.com/embed/reporting/ad970219-eae5-49b8-97f9-6c849b035aa4/page/LnVAC",
    },
    "mobile_voting": {
        "map": "https://datastudio.google.com/embed/reporting/5371860b-9891-4011-9156-b3beaf12b452/page/LnVAC",
    },
    "data_explorer": {
        "explorer": "https://datastudio.google.com/embed/reporting/240dce58-d939-4c52-83f2-4394b48d79cf/page/LnVAC",
    },
    "case_decisions": {
        "database": "https://datastudio.google.com/embed/reporting/248f5732-ddd3-4290-b702-e71a6d6b8055/page/LnVAC",
    },
    "overview": {
        "global_overview": "https://datastudio.google.com/embed/reporting/2eccc5dd-773d-43fd-9380-1c4b75df440e/page/LnVAC",
        "regional_overview": "https://datastudio.google.com/embed/reporting/875fecb9-a130-420f-9de7-a483877cca57/page/LnVAC",
        "country_details": "https://datastudio.google.com/embed/reporting/dd036d43-94e6-43be-9f53-a1c5bfdc014e/page/LnVAC",
    },
}

# Request headers to mimic a browser
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


async def fetch_page_with_retry(session: aiohttp.ClientSession, url: str, max_retries: int = 3) -> str:
    """Fetch HTML content from a URL with retry logic."""
    for attempt in range(max_retries):
        try:
            await asyncio.sleep(1)  # Rate limiting delay
            async with session.get(
                url, 
                headers=REQUEST_HEADERS,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=True
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
                elif resp.status == 429:
                    # Rate limited - wait and retry
                    wait_time = 2 ** attempt * 2
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    return ""
        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return ""
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return ""
    return ""


def parse_page_content(html: str, url: str) -> dict:
    """Parse HTML content and extract structured data."""
    soup = BeautifulSoup(html, 'html.parser')
    
    result = {
        "url": url,
        "title": "",
        "description": "",
        "methodology": "",
        "sections": [],
        "datastudio_embeds": [],
        "related_links": [],
        "types_of_svas": [],
    }
    
    # Extract title
    h1 = soup.find('h1')
    if h1:
        result["title"] = h1.get_text(strip=True)
    
    # Extract meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        result["description"] = meta_desc.get('content', '')
    
    # Extract methodology section
    methodology_heading = soup.find(['h2', 'h3'], string=re.compile('Methodology', re.I))
    if methodology_heading:
        content_parts = []
        for sibling in methodology_heading.find_next_siblings():
            if sibling.name in ['h2', 'h3']:
                break
            if sibling.name == 'p':
                text = sibling.get_text(strip=True)
                if text:
                    content_parts.append(text)
        result["methodology"] = ' '.join(content_parts)
    
    # Extract types of SVAs covered (if present)
    types_heading = soup.find(['h2', 'h3'], string=re.compile('Types of SVAs covered', re.I))
    if types_heading:
        types_list = types_heading.find_next('ul')
        if types_list:
            for li in types_list.find_all('li'):
                text = li.get_text(strip=True)
                if text:
                    result["types_of_svas"].append(text)
    
    # Extract all sections with content
    main = soup.find('main') or soup.find('article')
    if main:
        headings = main.find_all(['h2', 'h3'])
        for h in headings:
            text = h.get_text(strip=True)
            # Skip navigation/breadcrumb headings
            if text in ['Breadcrumb', 'Main navigation', 'Footer menu', 'Submit feedback', 
                        'Follow us', 'Get the best of International IDEA', 'Need Help?', 'Explore']:
                continue
            
            # Get content after this heading
            content_parts = []
            for sibling in h.find_next_siblings():
                if sibling.name in ['h2', 'h3', 'section']:
                    break
                if sibling.name == 'p':
                    txt = sibling.get_text(strip=True)
                    if txt:
                        content_parts.append(txt)
            
            if content_parts:
                result["sections"].append({
                    "heading": text,
                    "content": ' '.join(content_parts)
                })
    
    # Extract Data Studio embeds
    iframes = soup.find_all('iframe')
    for iframe in iframes:
        src = iframe.get('src', '')
        if 'datastudio.google.com' in src:
            # Extract report ID from URL
            report_id = src.split('/reporting/')[-1].split('/')[0] if '/reporting/' in src else ''
            result["datastudio_embeds"].append({
                "src": src,
                "title": iframe.get('title', ''),
                "report_id": report_id,
            })
    
    # Extract related links
    links = soup.find_all('a', href=True)
    seen_urls = set()
    for link in links:
        href = link['href']
        text = link.get_text(strip=True)
        if 'special-voting' in href and text and len(text) < 100:
            full_url = urljoin(BASE_URL, href)
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                result["related_links"].append({
                    "text": text,
                    "url": full_url
                })
    
    return result


async def get_overview_data(session: aiohttp.ClientSession) -> dict:
    """Get overview data from the main SVA page."""
    url = BASE_URL
    html = await fetch_page_with_retry(session, url)
    
    if not html:
        return {"error": "Failed to fetch overview page", "url": url}
    
    data = parse_page_content(html, url)
    
    # Add summary of available SVA types
    data["sva_types_available"] = list(SVA_PAGES.keys())
    
    return data


async def get_sva_type_data(session: aiohttp.ClientSession, sva_type: str) -> dict:
    """Get data for a specific SVA type."""
    if sva_type not in SVA_PAGES:
        return {"error": f"Unknown SVA type: {sva_type}. Available types: {list(SVA_PAGES.keys())}"}
    
    url = BASE_URL + SVA_PAGES[sva_type]
    html = await fetch_page_with_retry(session, url)
    
    if not html:
        return {"error": f"Failed to fetch {sva_type} page", "url": url}
    
    data = parse_page_content(html, url)
    data["sva_type"] = sva_type
    
    # Add Data Studio embed URLs
    if sva_type in DATASTUDIO_EMBEDS:
        data["datastudio_embeds_detailed"] = DATASTUDIO_EMBEDS[sva_type]
    
    return data


async def get_all_sva_data(session: aiohttp.ClientSession) -> dict:
    """Get data for all SVA types."""
    results = {}
    
    # Fetch pages sequentially with delays to avoid rate limiting
    for sva_type in SVA_PAGES.keys():
        data = await get_sva_type_data(session, sva_type)
        results[sva_type] = data
        await asyncio.sleep(0.5)  # Delay between requests
    
    return results


async def get_datastudio_info(session: aiohttp.ClientSession, sva_type: str = None) -> dict:
    """Get information about Data Studio embeds."""
    result = {
        "description": "Data is visualized through Google Data Studio (Looker Studio) embeds. "
                      "These interactive dashboards show country-level data on SVA implementation.",
        "note": "Direct data extraction from Data Studio requires JavaScript rendering. "
               "The embed URLs are provided for direct access.",
        "embeds": {},
    }
    
    if sva_type:
        if sva_type in DATASTUDIO_EMBEDS:
            result["embeds"][sva_type] = DATASTUDIO_EMBEDS[sva_type]
        else:
            result["error"] = f"Unknown SVA type: {sva_type}"
    else:
        result["embeds"] = DATASTUDIO_EMBEDS
    
    return result


async def search_sva_content(session: aiohttp.ClientSession, query: str) -> dict:
    """Search for content across all SVA pages."""
    query_lower = query.lower()
    results = []
    
    # Fetch all pages
    all_data = await get_all_sva_data(session)
    
    for sva_type, data in all_data.items():
        if "error" in data:
            continue
        
        matches = []
        
        # Search in title
        if query_lower in data.get("title", "").lower():
            matches.append({"field": "title", "value": data["title"]})
        
        # Search in description
        if query_lower in data.get("description", "").lower():
            matches.append({"field": "description", "value": data["description"]})
        
        # Search in methodology
        if query_lower in data.get("methodology", "").lower():
            matches.append({"field": "methodology", "snippet": data["methodology"][:300] + "..."})
        
        # Search in sections
        for section in data.get("sections", []):
            if query_lower in section.get("heading", "").lower():
                matches.append({"field": "section_heading", "value": section["heading"]})
            if query_lower in section.get("content", "").lower():
                matches.append({"field": "section_content", "heading": section["heading"], 
                              "snippet": section["content"][:300] + "..."})
        
        # Search in types of SVAs
        for sva in data.get("types_of_svas", []):
            if query_lower in sva.lower():
                matches.append({"field": "sva_type", "value": sva})
        
        if matches:
            results.append({
                "sva_type": sva_type,
                "title": data.get("title", ""),
                "url": data.get("url", ""),
                "matches": matches
            })
    
    return {
        "query": query,
        "total_results": len(results),
        "results": results
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the IDEA SVA data access skill.
    
    Functions:
    - get_overview: Get overview of all SVA data
    - get_sva_type: Get data for a specific SVA type
    - get_all: Get data for all SVA types
    - get_datastudio_info: Get Data Studio embed information
    - search: Search across all SVA content
    """
    function = params.get("function", "get_overview")
    
    async with aiohttp.ClientSession() as session:
        try:
            if function == "get_overview":
                result = await get_overview_data(session)
                
            elif function == "get_sva_type":
                sva_type = params.get("sva_type", "")
                if not sva_type:
                    result = {"error": "sva_type parameter required. Available types: " + ", ".join(SVA_PAGES.keys())}
                else:
                    result = await get_sva_type_data(session, sva_type)
                    
            elif function == "get_all":
                result = await get_all_sva_data(session)
                
            elif function == "get_datastudio_info":
                sva_type = params.get("sva_type")
                result = await get_datastudio_info(session, sva_type)
                
            elif function == "search":
                query = params.get("query", "")
                if not query:
                    result = {"error": "query parameter required for search"}
                else:
                    result = await search_sva_content(session, query)
                    
            else:
                result = {"error": f"Unknown function: {function}. Available functions: get_overview, get_sva_type, get_all, get_datastudio_info, search"}
                
        except Exception as e:
            result = {"error": str(e)}
    
    return result