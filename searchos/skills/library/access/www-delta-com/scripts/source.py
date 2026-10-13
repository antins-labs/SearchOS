"""
Delta Air Lines Baggage Information Skill

Fetches baggage policy information from Delta.com including:
- Carry-on baggage rules and allowances
- Checked baggage fees and policies
- Baggage FAQs

Uses direct HTTP requests to fetch HTML content as the site renders server-side.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Optional


async def fetch_page(url: str, session: aiohttp.ClientSession) -> str:
    """Fetch HTML content from a URL"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        if resp.status != 200:
            raise ValueError(f"Failed to fetch {url}: HTTP {resp.status}")
        return await resp.text()


def extract_structured_content(html: str, page_type: str) -> dict:
    """Extract structured content from HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find main content area
    main = soup.find('main')
    if not main:
        main = soup
    
    result = {
        'page_type': page_type,
        'title': '',
        'sections': [],
        'faqs': [],
        'lists': [],
    }
    
    # Get title
    h1 = main.find('h1')
    if h1:
        result['title'] = h1.get_text(strip=True)
    
    # Extract content blocks
    current_section = None
    
    for elem in main.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'p', 'ul', 'ol'], recursive=True):
        # Skip if nested inside another element we'll process
        if elem.find_parent(['p', 'ul', 'ol']):
            continue
        
        tag = elem.name
        
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5']:
            text = elem.get_text(strip=True)
            if text:
                current_section = {
                    'heading': text,
                    'level': tag,
                    'content': []
                }
                result['sections'].append(current_section)
        
        elif tag == 'p':
            text = elem.get_text(strip=True)
            if text and len(text) > 10:
                if current_section:
                    current_section['content'].append({
                        'type': 'paragraph',
                        'text': text
                    })
                else:
                    # Paragraph without section
                    if not result.get('intro'):
                        result['intro'] = []
                    result['intro'].append(text)
        
        elif tag in ['ul', 'ol']:
            items = []
            for li in elem.find_all('li', recursive=False):
                text = li.get_text(strip=True)
                if text:
                    items.append(text)
            
            if items:
                list_data = {
                    'items': items,
                    'type': tag
                }
                result['lists'].append(list_data)
                
                if current_section:
                    current_section['content'].append({
                        'type': 'list',
                        'items': items
                    })
    
    return result


def extract_faqs(html: str) -> list:
    """Extract FAQ questions and answers from Delta's FAQ page
    
    Delta uses a card/accordion structure:
    - Question is in card-header div (with expander-text or expander-news class)
    - Answer is in the next sibling div with class 'collapse' or 'panel-collapse'
    """
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main') or soup
    
    faqs = []
    seen_questions = set()
    
    # Find all card-header elements (contains the question)
    for card_header in main.find_all('div', class_='card-header'):
        # Get the question text
        question_text = card_header.get_text(strip=True)
        
        # Clean up question text (remove "Learn More" prefix if present)
        question_text = re.sub(r'^Learn More\s*', '', question_text)
        question_text = re.sub(r'^Lost Items FAQs\s*', '', question_text)
        question_text = re.sub(r'^20 Minute Bag Guarantee FAQs\s*', '', question_text)
        
        # Skip non-questions
        if not question_text or len(question_text) < 15:
            continue
        
        # Check if it looks like a question
        is_question = '?' in question_text or \
                     any(question_text.lower().startswith(q) for q in 
                         ['how ', 'what ', 'when ', 'where ', 'why ', 'are ', 'do ', 'can ', 'if ', 'does ', 'i '])
        
        if not is_question:
            continue
        
        # Skip duplicates
        if question_text in seen_questions:
            continue
        seen_questions.add(question_text)
        
        # Find the answer in the next sibling
        answer_div = card_header.find_next_sibling('div', class_=['collapse', 'panel-collapse'])
        
        if answer_div:
            answer_text = answer_div.get_text(strip=True, separator=' ')
            answer_text = re.sub(r'\s+', ' ', answer_text).strip()
            
            # Limit answer length
            if len(answer_text) > 500:
                answer_text = answer_text[:500] + '...'
            
            if len(answer_text) > 20:
                faqs.append({
                    'question': question_text,
                    'answer': answer_text
                })
    
    return faqs


def extract_carry_on_policy(html: str) -> dict:
    """Extract carry-on baggage policy details"""
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main') or soup
    
    policy = {
        'allowance': {},
        'size_restrictions': [],
        'approved_items': [],
        'free_items': [],
        'prohibited_items': [],
        'liquid_rules': [],
    }
    
    text = main.get_text(separator='\n', strip=True)
    
    # Extract allowance info
    allowance_match = re.search(r'Each passenger.*?can bring (\d+)\s*carry-on bag.*?(\d+)\s*personal item', text, re.I)
    if allowance_match:
        policy['allowance'] = {
            'carry_on_bags': int(allowance_match.group(1)),
            'personal_items': int(allowance_match.group(2))
        }
    
    # Extract size restrictions
    size_patterns = [
        r'(\d+["\']?\s*x\s*\d+["\']?\s*x\s*\d+["\']?)',
        r'(\d+)\s*linear\s*inches',
        r'not exceed (\d+)"\s*x\s*(\d+)"\s*x\s*(\d+)"'
    ]
    
    for pattern in size_patterns:
        match = re.search(pattern, text)
        if match:
            policy['size_restrictions'].append(match.group(0))
    
    # Find approved personal items list
    for ul in main.find_all('ul'):
        items = [li.get_text(strip=True) for li in ul.find_all('li', recursive=False)]
        items_text = ' '.join(items).lower()
        
        if 'purse' in items_text or 'laptop' in items_text or 'briefcase' in items_text:
            if 'approved' in str(ul.find_previous(['h3', 'h4', 'h5'])).lower():
                policy['approved_items'] = items
        
        if 'jacket' in items_text or 'umbrella' in items_text or 'duty-free' in items_text:
            if 'free' in str(ul.find_previous(['h3', 'h4', 'h5'])).lower():
                policy['free_items'] = items
        
        if 'liquid' in items_text or '3.4' in items_text or 'quart' in items_text:
            policy['liquid_rules'] = items
    
    # Look for prohibited items
    prohibited_keywords = ['prohibited', 'not allowed', "aren't allowed", 'cannot bring']
    for keyword in prohibited_keywords:
        if keyword in text.lower():
            # Find the section
            idx = text.lower().find(keyword)
            section = text[max(0, idx-100):idx+500]
            policy['prohibited_items'].append(section.strip())
    
    return policy


async def get_carry_on_info(session: aiohttp.ClientSession) -> dict:
    """Get carry-on baggage information"""
    url = "https://www.delta.com/us/en/baggage/carry-on-baggage"
    
    html = await fetch_page(url, session)
    
    return {
        'url': url,
        'content': extract_structured_content(html, 'carry-on'),
        'policy': extract_carry_on_policy(html),
        'raw_text': BeautifulSoup(html, 'html.parser').find('main').get_text(separator='\n', strip=True) if BeautifulSoup(html, 'html.parser').find('main') else ''
    }


async def get_baggage_faqs(session: aiohttp.ClientSession) -> dict:
    """Get baggage FAQs"""
    url = "https://www.delta.com/us/en/baggage/additional-baggage-information/baggage-faqs"
    
    html = await fetch_page(url, session)
    
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    
    return {
        'url': url,
        'faqs': extract_faqs(html),
        'content': extract_structured_content(html, 'faqs'),
        'raw_text': main.get_text(separator='\n', strip=True) if main else ''
    }


async def get_baggage_overview(session: aiohttp.ClientSession) -> dict:
    """Get baggage overview information"""
    url = "https://www.delta.com/us/en/baggage/overview"
    
    html = await fetch_page(url, session)
    
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.find('main')
    
    return {
        'url': url,
        'content': extract_structured_content(html, 'overview'),
        'raw_text': main.get_text(separator='\n', strip=True) if main else ''
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Delta baggage information query.
    
    Parameters:
        function: The function to call
            - get_carry_on_info: Get carry-on baggage rules and allowances
            - get_baggage_faqs: Get baggage frequently asked questions
            - get_baggage_overview: Get general baggage overview and fees
            - search_baggage_info: Search for specific baggage information
        
        query: (optional) Search query for search_baggage_info function
    
    Returns:
        Dictionary containing requested baggage information
    """
    function = params.get('function', '')
    
    try:
        async with aiohttp.ClientSession() as session:
            if function == 'get_carry_on_info':
                data = await get_carry_on_info(session)
                return {
                    'success': True,
                    'data': data
                }
            
            elif function == 'get_baggage_faqs':
                data = await get_baggage_faqs(session)
                return {
                    'success': True,
                    'data': data
                }
            
            elif function == 'get_baggage_overview':
                data = await get_baggage_overview(session)
                return {
                    'success': True,
                    'data': data
                }
            
            elif function == 'search_baggage_info':
                query = params.get('query', '').lower()
                
                if not query:
                    return {
                        'success': False,
                        'error': 'Query parameter required for search_baggage_info'
                    }
                
                # Fetch all pages and search through them
                results = []
                
                # Search carry-on info
                carry_on = await get_carry_on_info(session)
                if query in carry_on.get('raw_text', '').lower():
                    results.append({
                        'source': 'Carry-On Baggage',
                        'url': carry_on['url'],
                        'relevance': 'carry-on' if 'carry' in query or 'personal item' in query else 'general',
                        'policy': carry_on.get('policy', {}),
                        'sections': [s for s in carry_on.get('content', {}).get('sections', []) 
                                   if query in s.get('heading', '').lower() or 
                                   any(query in c.get('text', '').lower() for c in s.get('content', []))]
                    })
                
                # Search FAQs
                faqs = await get_baggage_faqs(session)
                matching_faqs = []
                for faq in faqs.get('faqs', []):
                    if query in faq['question'].lower() or query in faq['answer'].lower():
                        matching_faqs.append(faq)
                
                if matching_faqs:
                    results.append({
                        'source': 'Baggage FAQs',
                        'url': faqs['url'],
                        'matching_faqs': matching_faqs
                    })
                
                # Search overview
                overview = await get_baggage_overview(session)
                if query in overview.get('raw_text', '').lower():
                    results.append({
                        'source': 'Baggage Overview',
                        'url': overview['url'],
                        'sections': [s for s in overview.get('content', {}).get('sections', [])
                                   if query in s.get('heading', '').lower() or
                                   any(query in c.get('text', '').lower() for c in s.get('content', []))]
                    })
                
                return {
                    'success': True,
                    'query': query,
                    'results': results,
                    'total_sources': len(results)
                }
            
            else:
                return {
                    'success': False,
                    'error': f'Unknown function: {function}. Available functions: get_carry_on_info, get_baggage_faqs, get_baggage_overview, search_baggage_info'
                }
    
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'Network error: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Error: {str(e)}'
        }