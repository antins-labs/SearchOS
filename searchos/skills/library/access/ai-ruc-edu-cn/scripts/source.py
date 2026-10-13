"""
RUC AI Faculty Profile Scraper
Extracts faculty biographical and professional information from ai.ruc.edu.cn
"""

import aiohttp
import asyncio
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin, urlparse
import re


async def fetch_page(url: str, timeout: int = 20) -> str:
    """Fetch HTML content from a URL"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            resp.raise_for_status()
            return await resp.text()


def extract_section_title(content: str) -> tuple:
    """
    Extract section title from content that starts with uppercase header.
    Returns (title, remaining_content) or (None, content) if no title found.
    """
    # English section headers
    en_patterns = [
        'EDUCATION', 'WORK EXPERIENCE', 'RESEARCH INTERESTS', 
        'TEACHING', 'PUBLICATIONS', 'CONTACT'
    ]
    # Chinese section headers
    zh_patterns = [
        '教育经历', '工作经历', '研究方向', 
        '学生要求', '学术论文', '联系'
    ]
    
    for pattern in en_patterns + zh_patterns:
        if content.startswith(pattern):
            return pattern, content[len(pattern):]
    
    return None, content


def normalize_section_name(name: str) -> str:
    """Normalize section names to English"""
    mappings = {
        '教育经历': 'Education',
        '工作经历': 'Work Experience',
        '研究方向': 'Research Interests',
        '学生要求': 'Student Requirements',
        '学术论文': 'Publications',
        '联系': 'Contact',
        'EDUCATION': 'Education',
        'WORK EXPERIENCE': 'Work Experience',
        'RESEARCH INTERESTS': 'Research Interests',
        'TEACHING': 'Teaching',
        'PUBLICATIONS': 'Publications',
        'CONTACT': 'Contact'
    }
    return mappings.get(name, name)


def extract_email(text: str) -> Optional[str]:
    """Extract email address from text, handling obfuscated formats"""
    # Handle format like "jrwen(@)ruc.edu.cn"
    match = re.search(r'[\w\.-]+\s*\(@?\)\s*[\w\.-]+\.\w+', text)
    if match:
        # Clean up the email
        email = match.group(0)
        email = email.replace('(@)', '@').replace(' ', '')
        return email
    
    # Standard email format
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    if match:
        return match.group(0)
    
    return None


def extract_profile(soup: BeautifulSoup, url: str) -> Dict[str, Any]:
    """Extract faculty profile data from parsed HTML"""
    profile = {
        "url": url,
        "name": None,
        "position": None,
        "bio": None,
        "photo_url": None,
        "sections": {},
        "contact": {},
        "external_links": []
    }
    
    # Name from h1
    h1 = soup.find('h1')
    if h1:
        profile["name"] = h1.get_text(strip=True)
    
    # Position from aside span
    aside = soup.find('aside')
    if aside:
        span = aside.find('span')
        if span:
            profile["position"] = span.get_text(strip=True)
        
        # Photo from author-img div
        author_img = aside.find('div', class_='author-img')
        if author_img:
            img = author_img.find('img')
            if img:
                src = img.get('src', '')
                if src:
                    profile["photo_url"] = urljoin(url, src)
    
    # Bio from .text-desc
    desc = soup.find('div', class_='text-desc')
    if desc:
        profile["bio"] = desc.get_text(strip=True)
    
    # Sections from .colorlib-narrow-content
    # The section title is embedded at the start of the content
    content_divs = soup.find_all('div', class_='colorlib-narrow-content')
    
    for div in content_divs:
        content = div.get_text(strip=True)
        
        # Extract section title from content
        title, body = extract_section_title(content)
        
        if not title:
            continue
        
        # Normalize title
        norm_title = normalize_section_name(title)
        
        # Extract links from this section
        section_links = []
        for a in div.find_all('a'):
            href = a.get('href', '')
            text = a.get_text(strip=True)
            if href:
                full_url = urljoin(url, href)
                section_links.append({"text": text, "url": full_url})
        
        # Handle multiple publications sections
        if norm_title in profile["sections"]:
            # Append to existing section
            if norm_title == "Publications":
                existing = profile["sections"][norm_title]
                existing["content"] += "\n\n" + body
                existing["links"].extend(section_links)
            continue
        
        # Store section
        profile["sections"][norm_title] = {
            "content": body,
            "links": section_links
        }
        
        # Extract contact info from contact section
        if norm_title == "Contact":
            # Parse email
            email = extract_email(body)
            if email:
                profile["contact"]["email"] = email
            
            # Store full contact content
            profile["contact"]["raw"] = body
        
        # Collect external links
        for link in section_links:
            if 'http' in link['url'] and 'ai.ruc.edu.cn' not in link['url']:
                profile["external_links"].append(link)
    
    return profile


async def fetch_faculty_profile(url: str) -> Dict[str, Any]:
    """Fetch and extract a faculty profile from a URL"""
    try:
        html = await fetch_page(url)
        soup = BeautifulSoup(html, 'html.parser')
        profile = extract_profile(soup, url)
        
        return {
            "success": True,
            "profile": profile
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url
        }


async def search_faculty(base_url: str = "http://ai.ruc.edu.cn") -> Dict[str, Any]:
    """
    Note: This site doesn't have a searchable directory API.
    Faculty URLs need to be provided directly.
    """
    return {
        "success": False,
        "error": "Faculty directory search not available. Please provide direct faculty profile URLs.",
        "hint": "URLs follow patterns like: http://ai.ruc.edu.cn/academicfaculty/szdwn/{pinyin}/index.htm or http://ai.ruc.edu.cn/english/FACULTYn/{Name}/index.htm"
    }


async def execute(params: Dict[str, Any], ctx=None) -> Dict[str, Any]:
    """
    Main entry point for the skill.
    
    Functions:
    - get_profile: Extract faculty profile from a URL
      Required params: url
    - search: Check if faculty directory search is available (returns hint)
    """
    function = params.get("function", "")
    
    if function == "get_profile":
        url = params.get("url")
        if not url:
            return {
                "success": False,
                "error": "Missing required parameter: url"
            }
        
        # Validate URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return {
                "success": False,
                "error": "Invalid URL format"
            }
        
        return await fetch_faculty_profile(url)
    
    elif function == "search":
        return await search_faculty()
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available: get_profile, search"
        }