"""
SearchOS Access Skill for Renmin University of China GSAI Faculty Profiles
Fetches structured faculty profile data from gsai.ruc.edu.cn
"""

import re
from typing import Any
from playwright.async_api import async_playwright, Page


async def _extract_profile(page: Page, url: str) -> dict[str, Any]:
    """Extract all profile data from a faculty page."""
    
    result = {
        "success": True,
        "url": url,
        "name": None,
        "position": None,
        "bio": None,
        "education": [],
        "work_experience": [],
        "research_interests": None,
        "student_requirements": None,
        "courses": [],
        "contact": {},
        "links": {}
    }
    
    # Extract basic info from sidebar
    try:
        result["name"] = await page.locator('#colorlib-aside h1').inner_text()
    except:
        pass
    
    try:
        positions = await page.locator('#colorlib-aside .position').all_inner_texts()
        # Filter out empty positions and join
        non_empty = [p.strip() for p in positions if p.strip()]
        result["position"] = non_empty[0] if non_empty else None
    except:
        pass
    
    try:
        result["bio"] = await page.locator('.text-desc').inner_text()
    except:
        pass
    
    # Extract all sections
    sections = await page.locator('section.colorlib-about, section.colorlib-contact').all()
    
    for section in sections:
        try:
            heading = await section.locator('h2.colorlib-heading').inner_text()
            content = await section.locator('.col-md-12').inner_text()
            
            heading_lower = heading.lower()
            
            # Education section (教育经历 / EDUCATION)
            if '教育' in heading or 'education' in heading_lower:
                items = [item.strip() for item in content.split('\n') if item.strip()]
                result["education"] = items
            
            # Work experience section (工作经历 / WORK EXPERIENCE)
            elif '工作' in heading or 'work' in heading_lower:
                items = [item.strip() for item in content.split('\n') if item.strip()]
                result["work_experience"] = items
            
            # Research interests (研究方向 / RESEARCH)
            elif '研究' in heading or 'research' in heading_lower:
                result["research_interests"] = content.strip()
            
            # Student requirements (学生要求)
            elif '学生' in heading:
                result["student_requirements"] = content.strip()
            
            # Courses (教授课程 / TEACHING)
            elif '课程' in heading or 'teach' in heading_lower:
                items = [item.strip() for item in content.split('\n') if item.strip()]
                result["courses"] = items
            
            # Contact (联系 / CONTACT)
            elif '联系' in heading or 'contact' in heading_lower:
                contact = {}
                
                # Parse phone
                phone_match = re.search(r'电话[：:]\s*(.+?)(?:\n|$)', content)
                if phone_match:
                    val = phone_match.group(1).strip()
                    if val and val != '--':
                        contact["phone"] = val
                
                # Parse email
                email_match = re.search(r'邮箱[：:]\s*(.+?)(?:\n|$)', content)
                if email_match:
                    contact["email"] = email_match.group(1).strip()
                
                # Parse personal webpage
                web_match = re.search(r'个人网页[：:]\s*(.+?)(?:\n|$)', content)
                if web_match:
                    contact["webpage"] = web_match.group(1).strip()
                
                # Parse office address
                office_match = re.search(r'办公地址[：:]\s*(.+?)(?:\n|$)', content)
                if office_match:
                    contact["office"] = office_match.group(1).strip()
                
                result["contact"] = contact
            
            # Services section (English version)
            elif 'service' in heading_lower:
                result["research_interests"] = result.get("research_interests") or content.strip()
                
        except Exception as e:
            continue
    
    # Extract links from research interests section if present
    if result["research_interests"]:
        links = {}
        
        # Google Scholar
        scholar_match = re.search(r'(https://scholar\.google\.com[^\s\n]+)', result["research_interests"])
        if scholar_match:
            links["google_scholar"] = scholar_match.group(1)
        
        # Group website
        group_match = re.search(r'小组主页[：:]\s*([^\n]+)', result["research_interests"])
        if group_match:
            links["group_website"] = group_match.group(1).strip()
        
        # Zhihu
        zhihu_match = re.search(r'(https://www\.zhihu\.com[^\s\n]+)', result["research_interests"])
        if zhihu_match:
            links["zhihu"] = zhihu_match.group(1)
        
        result["links"] = links
    
    return result


async def _fetch_profile(url: str, lang: str = "zh") -> dict[str, Any]:
    """Fetch and parse a faculty profile page."""
    
    # Validate URL belongs to gsai.ruc.edu.cn
    if not url.startswith('https://gsai.ruc.edu.cn/'):
        return {
            "success": False,
            "error": "URL must be from gsai.ruc.edu.cn domain",
            "url": url
        }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                locale='zh-CN' if lang == 'zh' else 'en-US',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)  # Allow dynamic content to load
            
            # Check if page loaded correctly
            title = await page.title()
            if not title or 'error' in title.lower() or '404' in title.lower():
                return {
                    "success": False,
                    "error": f"Page failed to load: {title}",
                    "url": url
                }
            
            return await _extract_profile(page, url)
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "url": url
            }
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the GSAI faculty profile skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ('get_profile' or 'get_profile_english')
            - url: The faculty profile URL (e.g., 'https://gsai.ruc.edu.cn/chenxu')
                   or just the faculty name/slug (e.g., 'chenxu')

    
    Returns:
        Dictionary with structured faculty profile data
    """
    
    function = params.get("function", "")
    
    if function == "get_profile":
        url = params.get("url", "")
        
        if not url:
            return {
                "success": False,
                "error": "Missing required parameter: url"
            }
        
        # If just a name/slug provided, construct full URL
        if not url.startswith('http'):
            # Assume it's a faculty slug
            url = f"https://gsai.ruc.edu.cn/{url.strip('/')}"
        
        return await _fetch_profile(url, lang="zh")
    
    elif function == "get_profile_english":
        url = params.get("url", "")
        
        if not url:
            return {
                "success": False,
                "error": "Missing required parameter: url"
            }
        
        # If just a name/slug provided, construct full URL
        if not url.startswith('http'):
            url = f"https://gsai.ruc.edu.cn/english/{url.strip('/')}"
        elif '/english/' not in url:
            # Convert Chinese URL to English version
            url = url.replace('gsai.ruc.edu.cn/', 'gsai.ruc.edu.cn/english/')
        
        return await _fetch_profile(url, lang="en")
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available functions: get_profile, get_profile_english"
        }