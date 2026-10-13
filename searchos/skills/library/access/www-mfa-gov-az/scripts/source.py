"""
SearchOS Access Skill for Azerbaijan Ministry of Foreign Affairs (www.mfa.gov.az)
Extracts news articles and bilateral relations information.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs
import re


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute MFA Azerbaijan access skill.
    
    Functions:
    - get_news_article: Extract a specific news article by URL
    - list_news: List news articles with pagination
    - get_bilateral_relations: Extract bilateral relations info for a country
    """
    function = params.get("function", "")
    
    if function == "get_news_article":
        return await get_news_article(params)
    elif function == "list_news":
        return await list_news(params)
    elif function == "get_bilateral_relations":
        return await get_bilateral_relations(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def fetch_html(url: str, session: aiohttp.ClientSession) -> tuple[str, int]:
    """Fetch HTML content from URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    try:
        async with session.get(url, headers=headers, timeout=30, ssl=False) as response:
            html = await response.text()
            return html, response.status
    except Exception as e:
        return "", 0


def normalize_url(url: str, base_url: str = "https://www.mfa.gov.az") -> str:
    """Normalize URL to absolute form."""
    if not url:
        return ""
    if url.startswith('//'):
        return 'https:' + url
    if url.startswith('/'):
        return base_url + url
    if not url.startswith('http'):
        return base_url + '/' + url
    return url


async def get_news_article(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract a specific news article from MFA Azerbaijan.
    
    Parameters:
    - url: Full URL to the news article (e.g., https://www.mfa.gov.az/en/news/no28022)
    """
    url = params.get("url", "")
    
    if not url:
        return {"error": "Missing required parameter: url"}
    
    if 'mfa.gov.az' not in url:
        return {"error": "URL must be from mfa.gov.az domain"}
    
    if '/news/' not in url:
        return {"error": "URL must be a news article URL (containing /news/)"}
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_html(url, session)
        
        if status != 200 or not html:
            return {"error": f"Failed to fetch article (status: {status})", "url": url}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract article container
        article = soup.select_one('.section_articleInner_body')
        if not article:
            return {"error": "Could not find article content on page", "url": url}
        
        # Extract title
        title_el = article.select_one('.section_articleInner_body_head--header')
        title = title_el.get_text(strip=True) if title_el else ""
        
        # Extract content
        content_el = article.select_one('.section_articleInner_body_content--description')
        content = ""
        date = ""
        
        if content_el:
            # Get all paragraphs
            paragraphs = content_el.find_all('p')
            texts = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text:
                    texts.append(text)
            
            content = '\n\n'.join(texts)
            
            # Extract date from first paragraph (usually the date)
            if paragraphs:
                first_p = paragraphs[0].get_text(strip=True)
                # Date pattern: DD Month YYYY HH:MM
                date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4}\s+\d{2}:\d{2})', first_p)
                if date_match:
                    date = date_match.group(1)
        
        # Extract images
        images = []
        img_elements = article.find_all('img')
        for img in img_elements:
            src = img.get('src', '')
            src = normalize_url(src)
            if src and src not in images:
                images.append(src)
        
        # Extract article ID from URL
        article_id = ""
        id_match = re.search(r'/news/([^/?]+)', url)
        if id_match:
            article_id = id_match.group(1)
        
        # Get category if available
        category = ""
        cat_el = article.select_one('.section_articleInner_body_content_information--category')
        if not cat_el:
            # Try alternative selector
            cat_el = soup.select_one('.section_newsIn_item_content_information--category')
        if cat_el:
            category = cat_el.get_text(strip=True)
        
        return {
            "success": True,
            "url": url,
            "article_id": article_id,
            "title": title,
            "date": date,
            "category": category,
            "content": content,
            "images": images,
            "image_count": len(images)
        }


async def list_news(params: dict[str, Any]) -> dict[str, Any]:
    """
    List news articles from MFA Azerbaijan.
    
    Parameters:
    - page: Page number (default: 1)
    - lang: Language code - 'en' for English, 'az' for Azerbaijani (default: 'en')
    """
    page = params.get("page", 1)
    lang = params.get("lang", "en")
    
    try:
        page = int(page)
        if page < 1:
            page = 1
    except:
        page = 1
    
    base_url = f"https://www.mfa.gov.az/{lang}/news"
    if page > 1:
        url = f"{base_url}?page={page}"
    else:
        url = base_url
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_html(url, session)
        
        if status != 200 or not html:
            return {"error": f"Failed to fetch news list (status: {status})", "url": url}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract news items
        items = soup.select('.section_newsIn_item')
        
        articles = []
        for item in items:
            # URL
            article_url = item.get('href', '')
            article_url = normalize_url(article_url)
            
            # Title
            title_el = item.select_one('.section_newsIn_item_content--header')
            title = title_el.get_text(strip=True) if title_el else ""
            
            # Date
            date_el = item.select_one('.section_newsIn_item_content_information--date')
            date = date_el.get_text(strip=True) if date_el else ""
            
            # Category
            cat_el = item.select_one('.section_newsIn_item_content_information--category')
            category = cat_el.get_text(strip=True) if cat_el else ""
            
            # Description (if available)
            desc_el = item.select_one('.section_newsIn_item_content--description')
            description = desc_el.get_text(strip=True) if desc_el else ""
            
            # Article ID
            article_id = ""
            if article_url:
                id_match = re.search(r'/news/([^/?]+)', article_url)
                if id_match:
                    article_id = id_match.group(1)
            
            articles.append({
                "id": article_id,
                "url": article_url,
                "title": title,
                "date": date,
                "category": category,
                "description": description[:200] if description else ""
            })
        
        # Extract pagination info
        pagination = soup.select_one('.pagination')
        total_pages = 1
        if pagination:
            page_links = pagination.find_all('a', href=True)
            page_numbers = []
            for link in page_links:
                href = link.get('href', '')
                match = re.search(r'page=(\d+)', href)
                if match:
                    page_numbers.append(int(match.group(1)))
            if page_numbers:
                total_pages = max(page_numbers)
        
        return {
            "success": True,
            "url": url,
            "page": page,
            "total_pages": total_pages,
            "articles": articles,
            "count": len(articles)
        }


async def get_bilateral_relations(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract bilateral relations information for a specific country.
    
    Parameters:
    - url: Full URL to the bilateral relations page (e.g., https://www.mfa.gov.az/en/category/africa/chad)
    - region: Region name (e.g., 'africa', 'asia', 'europe') - used if url not provided
    - country: Country slug (e.g., 'chad', 'pakistan') - used if url not provided
    - lang: Language code (default: 'en')
    """
    url = params.get("url", "")
    region = params.get("region", "")
    country = params.get("country", "")
    lang = params.get("lang", "en")
    
    if not url:
        if region and country:
            url = f"https://www.mfa.gov.az/{lang}/category/{region}/{country}"
        else:
            return {"error": "Either 'url' or both 'region' and 'country' parameters are required"}
    
    if 'mfa.gov.az' not in url:
        return {"error": "URL must be from mfa.gov.az domain"}
    
    async with aiohttp.ClientSession() as session:
        html, status = await fetch_html(url, session)
        
        if status != 200 or not html:
            return {"error": f"Failed to fetch page (status: {status})", "url": url}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract content container
        content = soup.select_one('.page_content')
        if not content:
            # Try alternative
            content = soup.select_one('.section_articleInner_body_content')
        
        if not content:
            return {"error": "Could not find content on page", "url": url}
        
        # Extract title (usually first strong or heading text)
        title = ""
        # Country name is typically at the beginning
        text = content.get_text(strip=True)
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) < 100:
                title = line
                break
        
        # Extract full content
        paragraphs = []
        for p in content.find_all('p'):
            text = p.get_text(strip=True)
            if text and text not in ['Share this page']:
                paragraphs.append(text)
        
        # If no paragraphs, get all text
        if not paragraphs:
            full_text = content.get_text(separator='\n', strip=True)
            # Remove "Share this page" text
            full_text = full_text.replace('Share this page', '').strip()
            paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]
        
        # Join content
        content_text = '\n\n'.join(paragraphs)
        
        # Extract specific sections
        sections = {}
        current_section = "general"
        section_content = []
        
        for p in paragraphs:
            text = p.strip()
            # Check for section headers (typically short lines ending with specific patterns)
            if text and len(text) < 150:
                lower = text.lower()
                if any(kw in lower for kw in ['visit', 'relations', 'agreement', 'treaty', 'cooperation', 'contact', 'embassy', 'ambassador']):
                    # Save previous section
                    if section_content:
                        sections[current_section] = '\n'.join(section_content)
                    current_section = text
                    section_content = []
                    continue
            section_content.append(text)
        
        # Save last section
        if section_content:
            sections[current_section] = '\n'.join(section_content)
        
        # Extract country name from URL
        country_name = ""
        url_parts = url.rstrip('/').split('/')
        if len(url_parts) > 0:
            country_name = url_parts[-1].replace('-', ' ').title()
        
        # Extract region from URL
        region_name = ""
        if 'africa' in url:
            region_name = "Africa"
        elif 'asia' in url:
            region_name = "Asia"
        elif 'europe' in url:
            region_name = "Europe"
        elif 'america' in url:
            region_name = "Americas"
        
        return {
            "success": True,
            "url": url,
            "country": country_name or title,
            "region": region_name,
            "title": title,
            "content": content_text,
            "sections": sections if len(sections) > 1 else {},
            "paragraphs": paragraphs
        }