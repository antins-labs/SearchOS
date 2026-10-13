"""
SearchOS Access Skill for CPPCC National Committee Membership Roster
Extracts the complete list of members from en.cppcc.gov.cn
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any


async def fetch_page(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from a URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=timeout) as response:
            response.raise_for_status()
            return await response.text()


def clean_name(name: str) -> str:
    """Clean a name string by normalizing whitespace and removing non-breaking spaces."""
    # Replace non-breaking spaces with regular spaces
    name = name.replace('\xa0', ' ')
    # Normalize multiple spaces to single space
    name = re.sub(r'\s+', ' ', name)
    return name.strip()


def parse_names_from_text(text: str) -> list[str]:
    """
    Parse comma-separated names, respecting parentheses.
    
    Names may contain annotations like:
    - (female)
    - (military)
    - (Hui ethnicity)
    - (female, Zhejiang province)
    """
    names = []
    current = ""
    paren_depth = 0
    
    for char in text:
        if char == '(':
            paren_depth += 1
            current += char
        elif char == ')':
            paren_depth -= 1
            current += char
        elif char == ',' and paren_depth == 0:
            if current.strip():
                names.append(clean_name(current))
            current = ""
        else:
            current += char
    
    if current.strip():
        names.append(clean_name(current))
    
    return names


def extract_membership_roster(html: str) -> dict:
    """
    Extract the complete membership roster from the HTML.
    
    Returns a dict with:
    - total_count: int
    - categories: list of dicts with name, expected_count, actual_count, names
    """
    soup = BeautifulSoup(html, 'html.parser')
    paras = soup.find_all('p')
    
    categories = []
    current_category = None
    
    for p in paras:
        text = p.get_text(strip=True)
        if not text:
            continue
        
        # Check if this is a category header (e.g., "The Communist Party of China (99 members)")
        match = re.search(r'^(.+?)\s*\((\d+)\s*members?\)', text, re.IGNORECASE)
        if match:
            if current_category:
                categories.append(current_category)
            
            current_category = {
                'name': match.group(1).strip(),
                'expected_count': int(match.group(2)),
                'names': []
            }
        elif current_category and text and not text.startswith('The following'):
            # This is a names paragraph
            names = parse_names_from_text(text)
            current_category['names'].extend(names)
    
    # Add the last category
    if current_category:
        categories.append(current_category)
    
    # Calculate totals
    total_expected = sum(c['expected_count'] for c in categories)
    total_extracted = sum(len(c['names']) for c in categories)
    
    return {
        'total_expected': total_expected,
        'total_extracted': total_extracted,
        'categories_count': len(categories),
        'categories': [
            {
                'name': c['name'],
                'expected_count': c['expected_count'],
                'actual_count': len(c['names']),
                'names': c['names']
            }
            for c in categories
        ]
    }


def get_page_metadata(html: str) -> dict:
    """Extract page metadata like title and description."""
    soup = BeautifulSoup(html, 'html.parser')
    
    title = None
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
    
    description = None
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        description = meta_desc.get('content', '').strip()
    
    return {
        'title': title,
        'description': description
    }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the SearchOS skill.
    
    Functions:
    - get_roster: Extract the complete membership roster
    - get_categories: Get list of categories with member counts (without names)
    - get_category: Get members of a specific category by name
    - search_members: Search for members by name pattern
    - get_metadata: Get page metadata
    """
    function = params.get('function', '')
    
    if function == 'get_roster':
        url = params.get('url', 'http://en.cppcc.gov.cn/2023-03/08/c_867239.htm')
        
        try:
            html = await fetch_page(url)
            roster = extract_membership_roster(html)
            metadata = get_page_metadata(html)
            
            return {
                'success': True,
                'metadata': metadata,
                'data': roster
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    elif function == 'get_categories':
        url = params.get('url', 'http://en.cppcc.gov.cn/2023-03/08/c_867239.htm')
        
        try:
            html = await fetch_page(url)
            roster = extract_membership_roster(html)
            
            # Return categories without full name lists
            categories_summary = [
                {
                    'name': c['name'],
                    'expected_count': c['expected_count'],
                    'actual_count': c['actual_count']
                }
                for c in roster['categories']
            ]
            
            return {
                'success': True,
                'data': {
                    'total_expected': roster['total_expected'],
                    'total_extracted': roster['total_extracted'],
                    'categories_count': roster['categories_count'],
                    'categories': categories_summary
                }
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    elif function == 'get_category':
        url = params.get('url', 'http://en.cppcc.gov.cn/2023-03/08/c_867239.htm')
        category_name = params.get('category_name', '')
        
        if not category_name:
            return {
                'success': False,
                'error': 'category_name parameter is required'
            }
        
        try:
            html = await fetch_page(url)
            roster = extract_membership_roster(html)
            
            # Find matching category (case-insensitive partial match)
            matching = None
            for c in roster['categories']:
                if category_name.lower() in c['name'].lower():
                    matching = c
                    break
            
            if not matching:
                return {
                    'success': False,
                    'error': f'Category not found: {category_name}',
                    'available_categories': [c['name'] for c in roster['categories']]
                }
            
            return {
                'success': True,
                'data': matching
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    elif function == 'search_members':
        url = params.get('url', 'http://en.cppcc.gov.cn/2023-03/08/c_867239.htm')
        query = params.get('query', '')
        
        if not query:
            return {
                'success': False,
                'error': 'query parameter is required'
            }
        
        try:
            html = await fetch_page(url)
            roster = extract_membership_roster(html)
            
            # Search for members (case-insensitive)
            query_lower = query.lower()
            results = []
            
            for category in roster['categories']:
                for name in category['names']:
                    if query_lower in name.lower():
                        results.append({
                            'name': name,
                            'category': category['name']
                        })
            
            return {
                'success': True,
                'data': {
                    'query': query,
                    'total_results': len(results),
                    'results': results
                }
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    elif function == 'get_metadata':
        url = params.get('url', 'http://en.cppcc.gov.cn/2023-03/08/c_867239.htm')
        
        try:
            html = await fetch_page(url)
            metadata = get_page_metadata(html)
            
            return {
                'success': True,
                'data': metadata
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': [
                'get_roster',
                'get_categories', 
                'get_category',
                'search_members',
                'get_metadata'
            ]
        }