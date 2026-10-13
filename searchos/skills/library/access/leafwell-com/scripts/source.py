"""
Leafwell Marijuana Legal Status Scraper

Extracts structured legal status information from Leafwell's "Is Marijuana Legal in X?" articles.
"""

import asyncio
import aiohttp
import re
import json
from typing import Any, Optional
from bs4 import BeautifulSoup


async def fetch_page(url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """Fetch HTML content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.text()
            else:
                return None
    except Exception as e:
        return None


def extract_legal_status(text: str, description: str = None) -> dict:
    """Extract legal status indicators from text content."""
    text_lower = text.lower()
    if description:
        text_lower = description.lower() + " " + text_lower
    
    status = {
        "medical": None,
        "recreational": None,
        "cbd": None,
        "cultivation": None,
    }
    
    # Check for combined medical and recreational status
    combined_pattern = r"medical\s+(?:and\s+)?recreational\s+(?:marijuana|cannabis|weed|use)\s+(?:is\s+)?(?:both\s+)?(illegal|legal|decriminalized|prohibited)"
    match = re.search(combined_pattern, text_lower)
    if match:
        status["medical"] = match.group(1)
        status["recreational"] = match.group(1)
    
    # Medical status patterns
    if not status["medical"]:
        medical_patterns = [
            r"medical\s+(?:marijuana|cannabis|weed|use)\s+(?:is\s+)?(?:currently\s+)?(illegal|legal|decriminalized|prohibited)",
            r"(?:illegal|legal|decriminalized|prohibited)\s+(?:for\s+)?medical\s+(?:marijuana|cannabis|use|purposes)",
        ]
        for pattern in medical_patterns:
            match = re.search(pattern, text_lower)
            if match:
                status["medical"] = match.group(1)
                break
    
    # Recreational status patterns
    if not status["recreational"]:
        rec_patterns = [
            r"recreational\s+(?:marijuana|cannabis|weed|use)\s+(?:is\s+)?(?:currently\s+)?(illegal|legal|decriminalized|prohibited)",
            r"(?:illegal|legal|decriminalized|prohibited)\s+(?:for\s+)?recreational\s+(?:marijuana|cannabis|use|purposes)",
        ]
        for pattern in rec_patterns:
            match = re.search(pattern, text_lower)
            if match:
                status["recreational"] = match.group(1)
                break
    
    # CBD status patterns
    cbd_patterns = [
        r"(?:cbd|cannabidiol)[\s\w]*?(?:is\s+)?(illegal|legal|banned|prohibited)",
        r"(?:illegal|legal|banned|prohibited)[\s\w]*?(?:cbd|cannabidiol)",
    ]
    for pattern in cbd_patterns:
        match = re.search(pattern, text_lower)
        if match:
            status["cbd"] = match.group(1)
            break
    
    # Cultivation status patterns
    grow_patterns = [
        r"(?:it is\s+)?(illegal|legal|prohibited)\s+(?:to\s+)?(?:grow|cultivate)",
        r"(?:grow|growing|cultivation|cultivate)[\s\w]*?(?:is\s+)?(illegal|legal|prohibited)",
    ]
    for pattern in grow_patterns:
        match = re.search(pattern, text_lower)
        if match:
            status["cultivation"] = match.group(1)
            break
    
    # If we still don't have status, check the description for general statements
    if description and (status["medical"] is None or status["recreational"] is None):
        desc_lower = description.lower()
        
        # Check if description says "illegal for medical and recreational purposes"
        if "illegal" in desc_lower:
            if "medical and recreational" in desc_lower or "both" in desc_lower:
                if status["medical"] is None:
                    status["medical"] = "illegal"
                if status["recreational"] is None:
                    status["recreational"] = "illegal"
            elif "medical" in desc_lower and status["medical"] is None:
                status["medical"] = "illegal"
            elif "recreational" in desc_lower and status["recreational"] is None:
                status["recreational"] = "illegal"
        
        # Check for "legal" statements
        if "legal" in desc_lower:
            if "medical" in desc_lower and "illegal" not in desc_lower and status["medical"] is None:
                # Check for context like "legalized medical marijuana"
                if "legalized" in desc_lower or "legal for medical" in desc_lower:
                    status["medical"] = "legal"
    
    return status


def extract_penalties(text: str) -> list:
    """Extract penalty information from text."""
    penalties = []
    
    patterns = [
        r"((?:up to|minimum|maximum)?\s*[\d]+\s*(?:years?|months?)\s*(?:in\s+)?(?:prison|jail))",
        r"((?:fine|fines)\s*(?:of\s+)?[\w\s\$,\\d]+)",
        r"(death\s+(?:penalty|sentence))",
        r"((?:lengthy|heavy|severe|harsh)[\s\w]*(?:prison|jail|sentence|fine|penalty))",
        r"(deportation[\s\w]*)",
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            if m and len(m) > 5:
                clean = m.strip()
                if clean not in penalties:
                    penalties.append(clean)
    
    return penalties[:10]  # Limit to 10 items


def parse_article(html: str, url: str) -> dict:
    """Parse article HTML and extract structured legal information."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract metadata
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    description = meta_desc.get('content') if meta_desc else None
    
    # Extract JSON-LD
    json_ld_data = {}
    script = soup.find('script', type='application/ld+json')
    if script:
        try:
            json_ld_data = json.loads(script.string) or {}
        except:
            pass
    
    # Extract title
    title = json_ld_data.get('headline')
    if not title:
        title_tag = soup.find('h1')
        title = title_tag.get_text(strip=True) if title_tag else None
    
    # Clean title - remove " - Leafwell" suffix if present
    if title:
        title = re.sub(r'\s*-\s*Leafwell\s*$', '', title)
    
    # Extract country name from title
    country = None
    if title:
        # Pattern: "Is Marijuana Legal in X?"
        match = re.search(r'Is Marijuana Legal in ([^\?]+)\??', title, re.IGNORECASE)
        if match:
            country = match.group(1).strip()
    
    # Extract article content
    article = soup.find('article')
    
    sections = []
    all_text = []
    
    if article:
        current_section = None
        
        for element in article.find_all(['h2', 'h3', 'p', 'ul', 'ol'], recursive=True):
            if element.name in ['h2', 'h3']:
                if current_section:
                    sections.append(current_section)
                current_section = {
                    'heading': element.get_text(strip=True),
                    'paragraphs': [],
                    'list_items': []
                }
            elif current_section and element.name == 'p':
                text = element.get_text(strip=True)
                if text and len(text) > 10:
                    current_section['paragraphs'].append(text)
                    all_text.append(text)
            elif current_section and element.name in ['ul', 'ol']:
                items = [li.get_text(strip=True) for li in element.find_all('li') if li.get_text(strip=True)]
                if items:
                    current_section['list_items'].extend(items)
                    all_text.extend(items)
        
        if current_section:
            sections.append(current_section)
    
    # Combine all text for analysis
    full_text = ' '.join(all_text)
    
    # Extract legal status
    legal_status = extract_legal_status(full_text, description)
    
    # Extract penalties
    penalties = extract_penalties(full_text)
    
    # Extract key facts (first paragraphs from first section)
    key_facts = []
    if sections:
        for p in sections[0].get('paragraphs', [])[:3]:
            if len(p) > 30:
                key_facts.append(p)
    
    # Build structured result
    result = {
        "country": country,
        "url": url,
        "title": title,
        "description": description,
        "author": json_ld_data.get('author', [{}])[0].get('name') if json_ld_data.get('author') else None,
        "date_published": json_ld_data.get('datePublished'),
        "date_modified": json_ld_data.get('dateModified'),
        "legal_status": legal_status,
        "penalties": penalties if penalties else None,
        "key_facts": key_facts if key_facts else None,
        "sections": [
            {
                "heading": s['heading'],
                "paragraphs": s['paragraphs'],
                "list_items": s['list_items'] if s['list_items'] else None
            }
            for s in sections
        ],
        "raw_text": full_text[:5000] if full_text else None  # First 5000 chars
    }
    
    # Clean up None values in sections
    for s in result['sections']:
        if not s['list_items']:
            del s['list_items']
    
    # Remove empty sections
    result['sections'] = [s for s in result['sections'] if s['paragraphs'] or s.get('list_items')]
    
    return result


async def get_legal_status_by_country(country: str, session: aiohttp.ClientSession) -> dict:
    """Get legal status information for a specific country."""
    # Build URL from country name
    country_slug = country.lower().strip()
    country_slug = re.sub(r'[^a-z0-9\s-]', '', country_slug)
    country_slug = re.sub(r'\s+', '-', country_slug)
    
    url = f"https://leafwell.com/blog/is-marijuana-legal-in-{country_slug}"
    
    html = await fetch_page(url, session)
    
    if not html:
        return {
            "error": f"Could not fetch page for country: {country}",
            "url": url,
            "country": country
        }
    
    result = parse_article(html, url)
    result['query_country'] = country
    
    return result


async def get_legal_status_by_url(url: str, session: aiohttp.ClientSession) -> dict:
    """Get legal status information from a specific Leafwell URL."""
    html = await fetch_page(url, session)
    
    if not html:
        return {
            "error": f"Could not fetch page: {url}",
            "url": url
        }
    
    return parse_article(html, url)


async def search_countries(query: str, session: aiohttp.ClientSession) -> dict:
    """Search for country articles (limited functionality - returns URL pattern info)."""
    # This is a placeholder - Leafwell doesn't have a search API we can easily use
    # We'll return information about how to construct URLs
    
    return {
        "note": "Leafwell does not provide a public search API. Use get_by_country with a specific country name.",
        "url_pattern": "https://leafwell.com/blog/is-marijuana-legal-in-{country-slug}",
        "example": "For 'United States', use: https://leafwell.com/blog/is-marijuana-legal-in-the-united-states",
        "query_received": query
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Leafwell legal status scraper.
    
    Parameters:
        function: The function to call (get_by_country, get_by_url, search)
        country: Country name (for get_by_country)
        url: Full URL to a Leafwell article (for get_by_url)
        query: Search query (for search - limited functionality)
    
    Returns:
        Structured legal status information
    """
    function = params.get("function", "")
    
    async with aiohttp.ClientSession() as session:
        if function == "get_by_country":
            country = params.get("country")
            if not country:
                return {"error": "Missing required parameter: country"}
            
            return await get_legal_status_by_country(country, session)
        
        elif function == "get_by_url":
            url = params.get("url")
            if not url:
                return {"error": "Missing required parameter: url"}
            
            # Validate URL is from leafwell.com
            if "leafwell.com" not in url:
                return {"error": "URL must be from leafwell.com domain"}
            
            return await get_legal_status_by_url(url, session)
        
        elif function == "search":
            query = params.get("query")
            if not query:
                return {"error": "Missing required parameter: query"}
            
            return await search_countries(query, session)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "available_functions": ["get_by_country", "get_by_url", "search"]
            }