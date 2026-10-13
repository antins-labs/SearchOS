"""
SearchOS Access Skill for China Zhi Gong Party (致公党) Official Website
Website: https://www.zg.org.cn

This skill provides access to:
1. Current leadership information (现任领导)
2. Historical leadership by term (历届领导)
3. Central news articles (中央要闻)
4. Individual leader profiles
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import Any, Optional
import re


async def fetch_page(session: aiohttp.ClientSession, url: str, headers: dict) -> Optional[str]:
    """Fetch HTML content from a URL"""
    try:
        async with session.get(url, headers=headers, timeout=30) as response:
            if response.status == 200:
                return await response.text()
            return None
    except Exception as e:
        return None


def parse_leadership_list(html: str, base_url: str) -> list[dict]:
    """Parse leadership list page and extract leader information"""
    soup = BeautifulSoup(html, 'html.parser')
    leaders = []
    
    items = soup.find_all('div', class_='nl-item')
    for item in items:
        leader = {}
        
        # Name and profile link
        title_div = item.find('div', class_='nl-title')
        if title_div:
            link = title_div.find('a')
            if link:
                leader['name'] = link.get_text(strip=True)
                leader['profile_url'] = urljoin(base_url, link.get('href'))
        
        # Image
        img = item.find('img')
        if img:
            leader['image_url'] = urljoin(base_url, img.get('src', ''))
        
        # Intro text
        rp_div = item.find('div', class_='nl-rp')
        if rp_div:
            text = rp_div.get_text(strip=True)
            if '[详细]' in text:
                text = text.split('[详细]')[0]
            leader['intro'] = text
            
            # Extract current position
            if '现任' in text:
                parts = text.split('现任')
                if len(parts) > 1:
                    position = '现任' + parts[1].split('。')[0]
                    leader['current_position'] = position
        
        # Date
        date_div = item.find('div', class_='nl-date')
        if date_div:
            leader['date'] = date_div.get_text(strip=True)
        
        if leader.get('name'):
            leaders.append(leader)
    
    return leaders


def parse_leader_profile(html: str, base_url: str) -> dict:
    """Parse individual leader profile page"""
    soup = BeautifulSoup(html, 'html.parser')
    profile = {}
    
    # Name and basic info from leader-block
    leader_block = soup.find('div', class_='leader-block')
    if leader_block:
        name_div = leader_block.find('div', class_='leader-name')
        if name_div:
            profile['name'] = name_div.get_text(strip=True)
        
        img = leader_block.find('img')
        if img:
            profile['image_url'] = urljoin(base_url, img.get('src', ''))
    
    # Full biography from TRS_Editor
    trs_editor = soup.find('div', class_='TRS_Editor')
    if trs_editor:
        full_text = trs_editor.get_text(strip=True, separator='\n')
        profile['full_bio'] = full_text
        
        # Parse structured biography
        lines = [l.strip() for l in full_text.split('\n') if l.strip()]
        
        if lines:
            # First line is usually the title
            profile['bio_title'] = lines[0]
            
            # Second paragraph is basic info
            if len(lines) > 1:
                profile['basic_info'] = lines[1]
                
                # Extract gender, ethnicity, birth date, etc.
                basic = lines[1]
                
                # Gender
                if '，男，' in basic:
                    profile['gender'] = '男'
                elif '，女，' in basic:
                    profile['gender'] = '女'
                
                # Birth date
                birth_match = re.search(r'(\d{4})年(\d{1,2})月生', basic)
                if birth_match:
                    profile['birth_year'] = birth_match.group(1)
                    profile['birth_month'] = birth_match.group(2)
                
                # Ethnicity
                ethnicity_match = re.search(r'，(汉族|回族|藏族|维吾尔族|苗族|彝族|壮族|布依族|朝鲜族|满族|侗族|瑶族|白族|土家族|哈尼族|哈萨克族|傣族|黎族|傈僳族|佤族|畲族|高山族|拉祜族|水族|东乡族|纳西族|景颇族|柯尔克孜族|土族|达斡尔族|仫佬族|羌族|布朗族|撒拉族|毛南族|仡佬族|锡伯族|阿昌族|普米族|塔吉克族|怒族|乌孜别克族|俄罗斯族|鄂温克族|德昂族|保安族|裕固族|京族|塔塔尔族|独龙族|鄂伦春族|赫哲族|门巴族|珞巴族|基诺族)人', basic)
                if ethnicity_match:
                    profile['ethnicity'] = ethnicity_match.group(1)
                
                # Native place
                place_match = re.search(r'人，', basic)
                if place_match:
                    start_idx = basic.find('，')
                    if start_idx >= 0:
                        after_first_comma = basic[start_idx+1:]
                        end_idx = after_first_comma.find('人，')
                        if end_idx >= 0:
                            profile['native_place'] = after_first_comma[:end_idx]
            
            # Career history (lines with dates)
            career = []
            for line in lines[2:]:
                if line and ('-' in line or '年' in line or '月' in line):
                    career.append(line)
            if career:
                profile['career_history'] = career
    
    # Breadcrumb
    breadcrumb = soup.find('div', class_='dq-position')
    if breadcrumb:
        profile['breadcrumb'] = breadcrumb.get_text(strip=True)
    
    return profile


def parse_news_list(html: str, base_url: str) -> list[dict]:
    """Parse news list page"""
    soup = BeautifulSoup(html, 'html.parser')
    news = []
    
    items = soup.find_all('div', class_='nl-item')
    for item in items:
        article = {}
        
        # Title and link
        title_div = item.find('div', class_='nl-title')
        if title_div:
            link = title_div.find('a')
            if link:
                article['title'] = link.get_text(strip=True)
                article['url'] = urljoin(base_url, link.get('href'))
        
        # Date
        date_div = item.find('div', class_='nl-date')
        if date_div:
            article['date'] = date_div.get_text(strip=True)
        
        # Preview text
        rp_div = item.find('div', class_='nl-rp')
        if rp_div:
            text = rp_div.get_text(strip=True)
            if '[详细]' in text:
                text = text.split('[详细]')[0]
            article['preview'] = text
        
        if article.get('title'):
            news.append(article)
    
    return news


def parse_article(html: str, base_url: str) -> dict:
    """Parse individual news article page"""
    soup = BeautifulSoup(html, 'html.parser')
    article = {}
    
    # Title
    title_div = soup.find('div', class_='news-title')
    if title_div:
        article['title'] = title_div.get_text(strip=True)
    
    # Date/source info
    info_div = soup.find('div', class_='news-info')
    if info_div:
        article['info'] = info_div.get_text(strip=True)
        
        # Extract date
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', article['info'])
        if date_match:
            article['date'] = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
    
    # Content
    content_div = soup.find('div', class_='TRS_Editor')
    if content_div:
        paragraphs = content_div.find_all('p')
        if paragraphs:
            article['paragraphs'] = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
        else:
            article['content'] = content_div.get_text(strip=True)
        
        # Images
        images = []
        for img in content_div.find_all('img'):
            images.append({
                'url': urljoin(base_url, img.get('src', '')),
                'alt': img.get('alt', '')
            })
        if images:
            article['images'] = images
    
    # Breadcrumb
    breadcrumb = soup.find('div', class_='dq-position')
    if breadcrumb:
        article['breadcrumb'] = breadcrumb.get_text(strip=True)
    
    return article


def parse_leadership_terms(html: str, base_url: str) -> list[dict]:
    """Parse leadership index page to extract all term links"""
    soup = BeautifulSoup(html, 'html.parser')
    terms = []
    
    # Find navigation for different terms
    # Looking for links like 第一届领导, 第二届领导, etc.
    links = soup.find_all('a', href=True)
    
    for link in links:
        text = link.get_text(strip=True)
        href = link.get('href', '')
        
        # Match term patterns
        if '届领导' in text or '现任领导' in text:
            term = {
                'name': text,
                'url': urljoin(base_url, href)
            }
            
            # Extract term number
            if '现任' in text:
                term['term'] = 'current'
            else:
                match = re.search(r'第(.+)届', text)
                if match:
                    term['term'] = match.group(1)
            
            if term not in terms:
                terms.append(term)
    
    return terms


async def get_current_leadership(session: aiohttp.ClientSession, headers: dict) -> dict:
    """Get current leadership list"""
    url = "https://www.zg.org.cn/zgdjj/ljld/dsljld/"
    html = await fetch_page(session, url, headers)
    
    if not html:
        return {"error": "Failed to fetch current leadership page", "success": False}
    
    leaders = parse_leadership_list(html, url)
    
    return {
        "success": True,
        "data": {
            "term": "第十六届",
            "term_name": "现任领导",
            "leaders": leaders,
            "total": len(leaders)
        }
    }


async def get_leader_profile(session: aiohttp.ClientSession, headers: dict, profile_url: str) -> dict:
    """Get individual leader profile"""
    html = await fetch_page(session, profile_url, headers)
    
    if not html:
        return {"error": "Failed to fetch leader profile page", "success": False}
    
    profile = parse_leader_profile(html, profile_url)
    
    if not profile:
        return {"error": "Failed to parse leader profile", "success": False}
    
    return {
        "success": True,
        "data": profile
    }


async def get_central_news(session: aiohttp.ClientSession, headers: dict, limit: int = 10) -> dict:
    """Get central news list"""
    url = "https://www.zg.org.cn/zyyw/"
    html = await fetch_page(session, url, headers)
    
    if not html:
        return {"error": "Failed to fetch central news page", "success": False}
    
    news = parse_news_list(html, url)
    
    if limit:
        news = news[:limit]
    
    return {
        "success": True,
        "data": {
            "news": news,
            "total": len(news)
        }
    }


async def get_article(session: aiohttp.ClientSession, headers: dict, article_url: str) -> dict:
    """Get individual news article"""
    html = await fetch_page(session, article_url, headers)
    
    if not html:
        return {"error": "Failed to fetch article page", "success": False}
    
    article = parse_article(html, article_url)
    
    if not article:
        return {"error": "Failed to parse article", "success": False}
    
    return {
        "success": True,
        "data": article
    }


async def get_leadership_history(session: aiohttp.ClientSession, headers: dict) -> dict:
    """Get all leadership terms"""
    url = "https://www.zg.org.cn/zgdjj/ljld/"
    html = await fetch_page(session, url, headers)
    
    if not html:
        return {"error": "Failed to fetch leadership history page", "success": False}
    
    # Parse navigation to find all terms
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find the kind_menu that contains leadership terms
    terms = []
    kind_menus = soup.find_all('div', class_='kind_menu')
    
    for menu in kind_menus:
        links = menu.find_all('a', href=True)
        for link in links:
            text = link.get_text(strip=True)
            href = link.get('href')
            
            if '届领导' in text or '现任领导' in text:
                term = {
                    'name': text,
                    'url': urljoin(url, href)
                }
                
                if '现任' in text:
                    term['term'] = 'current'
                else:
                    match = re.search(r'第(.+)届', text)
                    if match:
                        term['term'] = match.group(1)
                
                # Avoid duplicates
                if not any(t.get('url') == term['url'] for t in terms):
                    terms.append(term)
    
    return {
        "success": True,
        "data": {
            "terms": terms,
            "total": len(terms)
        }
    }


async def get_term_leadership(session: aiohttp.ClientSession, headers: dict, term_url: str) -> dict:
    """Get leadership for a specific term"""
    html = await fetch_page(session, term_url, headers)
    
    if not html:
        return {"error": "Failed to fetch term leadership page", "success": False}
    
    leaders = parse_leadership_list(html, term_url)
    
    # Get term name from breadcrumb
    soup = BeautifulSoup(html, 'html.parser')
    breadcrumb = soup.find('div', class_='dq-position')
    term_name = ""
    if breadcrumb:
        text = breadcrumb.get_text(strip=True)
        if '>' in text:
            term_name = text.split('>')[-1]
    
    return {
        "success": True,
        "data": {
            "term_name": term_name,
            "leaders": leaders,
            "total": len(leaders)
        }
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main execution function for the SearchOS skill
    
    Parameters:
    - function: The function to call
      - get_current_leadership: Get current leadership list
      - get_leader_profile: Get individual leader profile (requires profile_url)
      - get_central_news: Get central news list (optional: limit)
      - get_article: Get individual news article (requires article_url)
      - get_leadership_history: Get all leadership terms
      - get_term_leadership: Get leadership for a specific term (requires term_url)
    """
    
    function = params.get("function", "")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    
    async with aiohttp.ClientSession() as session:
        if function == "get_current_leadership":
            return await get_current_leadership(session, headers)
        
        elif function == "get_leader_profile":
            profile_url = params.get("profile_url")
            if not profile_url:
                return {"error": "profile_url parameter is required", "success": False}
            return await get_leader_profile(session, headers, profile_url)
        
        elif function == "get_central_news":
            limit = params.get("limit", 10)
            if isinstance(limit, str):
                limit = int(limit)
            return await get_central_news(session, headers, limit)
        
        elif function == "get_article":
            article_url = params.get("article_url")
            if not article_url:
                return {"error": "article_url parameter is required", "success": False}
            return await get_article(session, headers, article_url)
        
        elif function == "get_leadership_history":
            return await get_leadership_history(session, headers)
        
        elif function == "get_term_leadership":
            term_url = params.get("term_url")
            if not term_url:
                return {"error": "term_url parameter is required", "success": False}
            return await get_term_leadership(session, headers, term_url)
        
        else:
            return {
                "error": f"Unknown function: {function}",
                "success": False,
                "available_functions": [
                    "get_current_leadership",
                    "get_leader_profile",
                    "get_central_news",
                    "get_article",
                    "get_leadership_history",
                    "get_term_leadership"
                ]
            }