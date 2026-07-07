"""SearchOS access skill for museum.or.kr - Korean Museum Association member museum profiles."""

import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


async def get_browser_context() -> tuple[Any, Browser, BrowserContext, Page]:
    """Create a browser context and navigate to main page to pass cookie challenge."""
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='ko-KR',
    )
    page = await context.new_page()
    
    # Visit main page to pass the cookie challenge
    await page.goto('https://museum.or.kr/', wait_until='networkidle', timeout=30000)
    await asyncio.sleep(2)
    
    return playwright, browser, context, page


def parse_museum_html(html: str) -> dict[str, Any]:
    """Extract structured museum data from HTML.
    
    The site uses Elementor builder with icon-list widgets for labels
    and text-editor widgets for values.
    """
    
    data = {}
    
    # Museum name from heading (exclude category names like 회원관, 사립)
    name_match = re.search(r'<h4[^>]*elementor-heading-title[^>]*>([^<]+)</h4>', html)
    if name_match:
        name = name_match.group(1).strip()
        if name and name not in ['회원관', '사립', '국립', '공립', '대학', '전문']:
            data['name'] = name
    
    # Extract museum type (category like 사립, 국립, etc.)
    type_match = re.search(r'<h6[^>]*elementor-size-default[^>]*>(사립|국립|공립|대학|전문)</h6>', html)
    if type_match:
        data['museum_type'] = type_match.group(1)
    
    # Extract description from text editor widget (longest meaningful text)
    desc_pattern = r'elementor-widget-text-editor[^>]*>.*?<div class="elementor-widget-container">(.*?)</div>'
    text_editors = re.findall(desc_pattern, html, re.DOTALL)
    
    descriptions = []
    for editor in text_editors:
        text = re.sub(r'<[^>]+>', ' ', editor)
        text = ' '.join(text.split())
        if len(text) > 50 and not any(kw in text for kw in ['월-', '매주', ':', '|', '구 ', '02-']):
            descriptions.append(text)
    
    if descriptions:
        # Get the longest description
        data['description'] = max(descriptions, key=len)
    
    # Extract icon list items (labels)
    icon_lists = re.findall(r'elementor-icon-list[^>]*>(.*?)</ul>', html, re.DOTALL)
    labels = []
    for il in icon_lists:
        items = re.findall(r'elementor-icon-list-text">([^<]+)', il)
        labels.extend(items)
    
    # Extract text editor content (values) - short values only
    text_values = []
    for editor in text_editors:
        text = re.sub(r'<[^>]+>', ' ', editor)
        text = ' '.join(text.split())
        if text and len(text) < 100:
            text_values.append(text)
    
    # Map labels to values based on content patterns
    for i, label in enumerate(labels):
        label_clean = label.strip()
        
        if '관람안내' in label_clean or '운영시간' in label_clean or '관람시간' in label_clean:
            for val in text_values[:]:
                if re.search(r'\d{1,2}:\d{2}', val) or '시' in val:
                    data['hours'] = val
                    if val in text_values:
                        text_values.remove(val)
                    break
        
        elif '휴관일' in label_clean:
            for val in text_values[:]:
                if '요일' in val or '공휴일' in val or '월요일' in val or '일요일' in val or '휴' in val:
                    data['closed_days'] = val
                    if val in text_values:
                        text_values.remove(val)
                    break
        
        elif '입장료' in label_clean or '관람료' in label_clean:
            for val in text_values[:]:
                if '무료' in val or '원' in val or '확인' in val or '유료' in val:
                    data['admission_fee'] = val
                    if val in text_values:
                        text_values.remove(val)
                    break
        
        elif '주소' in label_clean or '소재지' in label_clean:
            for val in text_values[:]:
                if re.search(r'[구시동]\s', val) or '로 ' in val or '길 ' in val:
                    data['address'] = val
                    if val in text_values:
                        text_values.remove(val)
                    break
        
        elif '전화' in label_clean or '연락처' in label_clean:
            for val in text_values[:]:
                if '02-' in val or re.search(r'\d{2,3}-\d{3,4}-\d{4}', val):
                    data['phone_fax'] = val
                    if val in text_values:
                        text_values.remove(val)
                    break
    
    # Website link - look for 홈페이지 바로가기 or similar
    website_patterns = [
        r'<a[^>]*href="([^"]+)"[^>]*>\s*홈페이지\s*(?:바로가기)?\s*</a>',
        r'<a[^>]*href="([^"]+)"[^>]*>[^<]*홈페이지[^<]*</a>',
    ]
    
    for pattern in website_patterns:
        website_match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
        if website_match:
            data['website'] = website_match.group(1)
            break
    
    # Museum featured image - look for uploads images that are not logos
    # First try to find image with museum name in filename
    img_patterns = [
        r'<img[^>]*src="([^"]*(?:uploads|content)[^"]*(?:\.jpg|\.jpeg|\.png))"[^>]*alt="[^"]*미술관[^"]*"',
        r'<img[^>]*src="([^"]*(?:uploads|content)[^"]*(?:\.jpg|\.jpeg|\.png))"[^>]*class="[^"]*(?:featured|main|museum)[^"]*"',
        r'<img[^>]*class="[^"]*wp-post-image[^"]*"[^>]*src="([^"]+)"',
    ]
    
    for pattern in img_patterns:
        img_match = re.search(pattern, html, re.IGNORECASE)
        if img_match:
            img_url = img_match.group(1)
            # Clean the URL
            img_url = img_url.split('#')[0].split('?')[0]
            # Skip logo images
            if 'logo' not in img_url.lower():
                data['image_url'] = img_url
                break
    
    # Fallback: find any uploads image that looks like a museum photo (not logo, not icon)
    if 'image_url' not in data:
        all_imgs = re.findall(r'<img[^>]*src="([^"]*(?:uploads|content)[^"]*(?:\.jpg|\.jpeg|\.png))[^"]*"[^>]*>', html, re.IGNORECASE)
        for img_url in all_imgs:
            img_clean = img_url.split('#')[0].split('?')[0]
            # Skip logos and small images
            if 'logo' not in img_clean.lower() and 'icon' not in img_clean.lower():
                # Prefer larger images (check for 포스코미.jpg pattern - museum-specific)
                if '.jpg' in img_clean or '.jpeg' in img_clean:
                    data['image_url'] = img_clean
                    break
    
    return data


async def fetch_museum_profile(url: str) -> dict[str, Any]:
    """Fetch a museum profile from the given URL."""
    
    playwright = browser = context = page = None
    
    try:
        playwright, browser, context, page = await get_browser_context()
        
        # Navigate to museum page
        response = await page.goto(url, wait_until='networkidle', timeout=30000)
        
        if response.status != 200:
            return {
                'error': f'HTTP {response.status}',
                'url': url,
                'status': 'failed',
            }
        
        await asyncio.sleep(1)
        
        # Get page content
        html = await page.content()
        
        if len(html) < 1000 or '403 Forbidden' in html:
            return {
                'error': 'Access denied or empty content',
                'url': url,
                'status': 'failed',
            }
        
        # Extract structured data
        data = parse_museum_html(html)
        data['url'] = url
        data['status'] = 'success'
        
        return data
        
    except Exception as e:
        return {
            'error': str(e),
            'url': url,
            'status': 'failed',
        }
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


async def search_museums(query: str = '', limit: int = 20) -> dict[str, Any]:
    """Search for museums or list all museums.
    
    Note: The site doesn't have a comprehensive museum list or search API.
    This function attempts to find museums but may return limited results.
    For reliable access, use direct URLs with get_museum.
    """
    
    playwright = browser = context = page = None
    
    try:
        playwright, browser, context, page = await get_browser_context()
        
        # Try the museum member listing page
        await page.goto('https://museum.or.kr/museum-member/', wait_until='networkidle', timeout=30000)
        await asyncio.sleep(1)
        
        # Get all links
        all_links = await page.query_selector_all('a')
        
        museums = []
        seen_urls = set()
        
        for link in all_links:
            try:
                href = await link.get_attribute('href')
                text = await link.inner_text()
                text = text.strip()
                
                # Filter for museum profile pages
                if not href or not text:
                    continue
                if '/museum-member/' not in href:
                    continue
                # Skip the listing page itself
                if href.rstrip('/') in ['https://museum.or.kr/museum-member', 'https://museum.or.kr/museum-member/']:
                    continue
                # Skip menu items and navigation
                if len(text) < 2 or len(text) > 50:
                    continue
                if any(x in text for x in ['로그인', '회원가입', '검색', 'MENU', 'Menu', '←', '→']):
                    continue
                    
                # Normalize URL
                href = href.split('#')[0].rstrip('/')
                if not href.startswith('http'):
                    href = 'https://museum.or.kr' + href
                
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                
                # Filter by query if provided
                if query and query.lower() not in text.lower():
                    continue
                
                museums.append({
                    'name': text,
                    'url': href,
                })
                
                if len(museums) >= limit:
                    break
                    
            except Exception:
                continue
        
        return {
            'status': 'success',
            'count': len(museums),
            'query': query if query else None,
            'museums': museums,
            'note': 'Limited results. Use get_museum with direct URL for full profile.' if not museums else None,
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'status': 'failed',
        }
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Main entry point for the skill.
    
    Args:
        params: Must contain 'function' key with one of:
            - 'get_museum': Get a specific museum profile (requires 'url')
            - 'search_museums': Search/list museums (optional 'query' and 'limit')
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with status and data or error
    """
    
    function = params.get('function', '').strip().lower()
    
    if function == 'get_museum':
        url = params.get('url', '').strip()
        
        if not url:
            return {
                'error': 'Missing required parameter: url',
                'status': 'failed',
            }
        
        # Validate and normalize URL
        if 'museum.or.kr/museum-member/' not in url:
            return {
                'error': 'Invalid URL: must be a museum.or.kr/museum-member/ URL',
                'status': 'failed',
            }
        
        # Ensure URL has proper encoding
        if not url.endswith('/'):
            url = url + '/'
        
        return await fetch_museum_profile(url)
    
    elif function == 'search_museums':
        query = params.get('query', '').strip()
        try:
            limit = int(params.get('limit', 20))
            limit = min(max(1, limit), 100)  # Clamp between 1 and 100
        except (ValueError, TypeError):
            limit = 20
        
        return await search_museums(query=query, limit=limit)
    
    else:
        return {
            'error': f'Unknown function: {function}. Use "get_museum" or "search_museums".',
            'status': 'failed',
        }


if __name__ == '__main__':
    # Test the functions
    import json
    
    async def test():
        print("Testing get_museum - 포스코미술관...")
        result = await fetch_museum_profile('https://museum.or.kr/museum-member/%ED%8F%AC%EC%8A%A4%EC%BD%94%EB%AF%B8%EC%88%A0%EA%B4%80/')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        print("\n" + "="*80)
        print("Testing get_museum - 뮤지엄김치간...")
        result = await fetch_museum_profile('https://museum.or.kr/museum-member/뮤지엄김치간/')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        print("\n" + "="*80)
        print("Testing search_museums...")
        result = await search_museums(limit=10)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    asyncio.run(test())