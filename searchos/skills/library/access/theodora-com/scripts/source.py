"""
Theodora.com World Factbook Access Skill

Extracts country geography data from theodora.com CIA World Factbook pages.
Supports both world_fact_book_2024 and wfbcurrent URL patterns.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL."""
    try:
        async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                return await response.text()
            else:
                return None
    except Exception as e:
        return None


def parse_geography_content(html: str) -> dict:
    """Parse geography data from HTML content."""
    if not html:
        return {"error": "No HTML content to parse"}
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the main content div with class "html"
    content_div = soup.find('div', class_='html')
    
    if not content_div:
        return {"error": "Could not find main content div"}
    
    # Extract country name from title
    title = soup.find('title')
    country_name = ""
    if title:
        title_text = title.get_text(strip=True)
        # Pattern: "Russia Geography 2024, CIA World Factbook"
        match = re.match(r'^(.+?)\s+Geography', title_text)
        if match:
            country_name = match.group(1)
    
    # Extract all geography fields
    h3_tags = content_div.find_all('h3')
    geography_data = {
        "country": country_name,
        "fields": {}
    }
    
    for h3 in h3_tags:
        # Get field name (text inside the h3, possibly within an anchor)
        field_name = h3.get_text(strip=True)
        
        # Skip non-geography headers
        if field_name.lower() in ['definitions', 'source', 'feedback']:
            continue
        
        # Get the next paragraph(s) until the next h3
        value_parts = []
        next_elem = h3.find_next_sibling()
        
        while next_elem and next_elem.name != 'h3':
            if next_elem.name == 'p':
                # Get text, preserving line breaks from <br> tags
                text = next_elem.get_text(separator='\n', strip=True)
                if text:
                    value_parts.append(text)
            elif next_elem.name == 'div':
                text = next_elem.get_text(separator='\n', strip=True)
                if text:
                    value_parts.append(text)
            next_elem = next_elem.find_next_sibling()
        
        value = '\n'.join(value_parts) if value_parts else ''
        # Clean up excessive newlines
        value = re.sub(r'\n{3,}', '\n\n', value).strip()
        
        if field_name and value:
            geography_data["fields"][field_name] = value
    
    return geography_data


def parse_country_list(html: str) -> dict:
    """Parse list of available countries from the main index."""
    if not html:
        return {"error": "No HTML content to parse"}
    
    soup = BeautifulSoup(html, 'html.parser')
    
    countries = []
    links = soup.find_all('a', href=True)
    
    for link in links:
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Match country index pages
        if '/wfbcurrent/' in href and '/index.html' in href:
            # Extract country name from URL
            match = re.search(r'/wfbcurrent/([^/]+)/index\.html', href)
            if match:
                country_slug = match.group(1)
                countries.append({
                    "name": text,
                    "slug": country_slug,
                    "url": href
                })
    
    # Remove duplicates and sort
    seen = set()
    unique_countries = []
    for c in countries:
        if c['slug'] not in seen:
            seen.add(c['slug'])
            unique_countries.append(c)
    
    unique_countries.sort(key=lambda x: x['name'])
    
    return {
        "total": len(unique_countries),
        "countries": unique_countries[:100],  # Return first 100
        "note": "Showing first 100 countries. Use search to find specific countries."
    }


def parse_country_sections(html: str, country_slug: str) -> dict:
    """Parse available sections for a country from its index page."""
    if not html:
        return {"error": "No HTML content to parse"}
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract country name from title
    title = soup.find('title')
    country_name = ""
    if title:
        title_text = title.get_text(strip=True)
        match = re.match(r'^(.+?)\s+', title_text)
        if match:
            country_name = match.group(1)
    
    sections = []
    links = soup.find_all('a', href=True)
    
    for link in links:
        href = link.get('href', '')
        text = link.get_text(strip=True).lower()
        
        # Match section pages (e.g., russia_geography.html)
        if f'{country_slug}_' in href.lower() and '.html' in href:
            # Extract section name
            match = re.search(rf'{country_slug}_([^.]+)\.html', href, re.IGNORECASE)
            if match:
                section_name = match.group(1)
                sections.append({
                    "name": section_name.replace('_', ' ').title(),
                    "slug": section_name,
                    "url": href
                })
    
    # Remove duplicates
    seen = set()
    unique_sections = []
    for s in sections:
        if s['slug'] not in seen:
            seen.add(s['slug'])
            unique_sections.append(s)
    
    return {
        "country": country_name,
        "country_slug": country_slug,
        "sections": unique_sections
    }


async def get_geography(params: dict) -> dict:
    """Get geography data for a specific country."""
    country = params.get("country", "").strip().lower()
    if not country:
        return {"error": "Missing required parameter: country"}
    
    # Normalize country name to URL slug format
    country_slug = country.replace(' ', '_').replace('-', '_')
    
    # Try both URL patterns
    urls = [
        f"https://theodora.com/world_fact_book_2024/{country_slug}/{country_slug}_geography.html",
        f"https://theodora.com/wfbcurrent/{country_slug}/{country_slug}_geography.html"
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            html = await fetch_page(url, session)
            if html:
                result = parse_geography_content(html)
                if "error" not in result:
                    result["url"] = url
                    return result
        
        return {"error": f"Could not find geography data for country: {country}"}


async def get_geography_by_url(params: dict) -> dict:
    """Get geography data from a specific URL."""
    url = params.get("url", "").strip()
    if not url:
        return {"error": "Missing required parameter: url"}
    
    # Validate URL
    if 'theodora.com' not in url:
        return {"error": "URL must be from theodora.com domain"}
    
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(url, session)
        if html:
            result = parse_geography_content(html)
            result["url"] = url
            return result
        else:
            return {"error": f"Could not fetch page: {url}"}


async def list_countries(params: dict) -> dict:
    """List all available countries."""
    url = "https://theodora.com/wfb/"
    
    async with aiohttp.ClientSession() as session:
        html = await fetch_page(url, session)
        if html:
            return parse_country_list(html)
        else:
            return {"error": "Could not fetch country list"}


async def list_sections(params: dict) -> dict:
    """List available sections for a country."""
    country = params.get("country", "").strip().lower()
    if not country:
        return {"error": "Missing required parameter: country"}
    
    country_slug = country.replace(' ', '_').replace('-', '_')
    
    # Try both URL patterns
    urls = [
        f"https://theodora.com/world_fact_book_2024/{country_slug}/index.html",
        f"https://theodora.com/wfbcurrent/{country_slug}/index.html"
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            html = await fetch_page(url, session)
            if html:
                result = parse_country_sections(html, country_slug)
                if "error" not in result and result.get("sections"):
                    return result
        
        return {"error": f"Could not find country: {country}"}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the Theodora.com access skill.
    
    Dispatches based on the 'function' parameter.
    """
    function = params.get("function", "")
    
    if function == "get_geography":
        return await get_geography(params)
    elif function == "get_geography_by_url":
        return await get_geography_by_url(params)
    elif function == "list_countries":
        return await list_countries(params)
    elif function == "list_sections":
        return await list_sections(params)
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": [
                "get_geography - Get geography data for a country (requires: country)",
                "get_geography_by_url - Get geography data from a specific URL (requires: url)",
                "list_countries - List all available countries",
                "list_sections - List available sections for a country (requires: country)"
            ]
        }