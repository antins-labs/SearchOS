"""
Grokipedia Access Skill

Fetches and extracts structured content from Grokipedia wiki pages.
Grokipedia is a wiki/encyclopedia site with articles containing sections,
tables, lists, and other structured data.
"""

import httpx
from bs4 import BeautifulSoup, Tag
from typing import Any
import asyncio


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute Grokipedia page fetch and extraction.
    
    Parameters:
        function: One of 'get_page', 'search' (currently only 'get_page' supported)
        url: Full URL to Grokipedia page (e.g., https://grokipedia.com/page/example)
        slug: Page slug (e.g., 'i_am_gloria_world_tour') - used if url not provided
    
    Returns:
        Dict with success status, page data (title, abstract, sections, tables, metadata)
    """
    function = params.get('function', 'get_page')
    
    if function == 'get_page':
        return await get_page(params)
    elif function == 'search':
        return {
            'success': False,
            'error': 'Search function not implemented - use get_page with url or slug parameter',
            'hint': 'Grokipedia does not have a public search API. Use get_page with a known page URL or slug.'
        }
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': ['get_page']
        }


async def get_page(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch and parse a Grokipedia page.
    
    Parameters:
        url: Full URL to the page (optional)
        slug: Page slug (optional, used if url not provided)
    
    Returns:
        Structured page data with sections, tables, and metadata
    """
    url = params.get('url')
    slug = params.get('slug')
    
    if not url and not slug:
        return {
            'success': False,
            'error': 'Either url or slug parameter is required'
        }
    
    if not url:
        url = f'https://grokipedia.com/page/{slug}'
    
    # Validate URL
    if not url.startswith('https://grokipedia.com/'):
        return {
            'success': False,
            'error': 'URL must be from grokipedia.com domain'
        }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            
            if response.status_code == 404:
                return {
                    'success': False,
                    'error': 'Page not found',
                    'url': url,
                    'status_code': 404
                }
            
            if response.status_code != 200:
                return {
                    'success': False,
                    'error': f'HTTP error: {response.status_code}',
                    'url': url,
                    'status_code': response.status_code
                }
            
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            
            result = {
                'success': True,
                'url': str(response.url),
                'title': None,
                'slug': None,
                'abstract': None,
                'sections': [],
                'tables': [],
                'lists': [],
                'metadata': {},
                'categories': []
            }
            
            # Extract slug from URL
            if '/page/' in str(response.url):
                result['slug'] = str(response.url).split('/page/')[-1].split('?')[0].split('#')[0]
            
            # Find article container
            article = soup.find('article') or soup.find('main')
            
            if not article:
                result['success'] = False
                result['error'] = 'No article/main element found'
                return result
            
            # Extract title
            h1 = article.find('h1')
            if h1:
                result['title'] = h1.get_text(strip=True)
            
            # Extract page title from <title> tag as fallback
            if not result['title']:
                title_tag = soup.find('title')
                if title_tag:
                    title_text = title_tag.get_text(strip=True)
                    # Remove " — Grokipedia" suffix if present
                    if ' — Grokipedia' in title_text:
                        result['title'] = title_text.split(' — Grokipedia')[0]
            
            # Extract metadata
            metadata_selectors = {
                'description': ('meta', {'name': 'description'}),
                'keywords': ('meta', {'name': 'keywords'}),
                'og:title': ('meta', {'property': 'og:title'}),
                'og:description': ('meta', {'property': 'og:description'}),
            }
            
            for key, (tag, attrs) in metadata_selectors.items():
                elem = soup.find(tag, attrs)
                if elem and elem.get('content'):
                    # Clean up og:title
                    if key == 'og:title' and ' — Grokipedia' in elem['content']:
                        result['metadata'][key] = elem['content'].split(' — Grokipedia')[0]
                    else:
                        result['metadata'][key] = elem['content']
            
            # Parse and extract structured content
            result['sections'], result['tables'], result['lists'] = extract_content(article)
            
            # Extract abstract (first paragraph)
            first_para = article.find('span', class_=lambda x: x and 'mb-4' in x)
            if first_para:
                result['abstract'] = first_para.get_text(strip=True)
            
            # Extract categories if present (look for category links)
            category_links = soup.find_all('a', href=lambda x: x and '/category/' in x)
            for link in category_links:
                cat_text = link.get_text(strip=True)
                if cat_text and cat_text not in result['categories']:
                    result['categories'].append(cat_text)
            
            return result
            
    except httpx.TimeoutException:
        return {
            'success': False,
            'error': 'Request timed out',
            'url': url
        }
    except httpx.RequestError as e:
        return {
            'success': False,
            'error': f'Request error: {str(e)}',
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}',
            'url': url
        }


def extract_content(article: Tag) -> tuple[list, list, list]:
    """
    Extract sections, tables, and lists from the article element.
    
    Grokipedia uses a specific structure:
    - Headings (h1-h6) define sections
    - Paragraphs are in <span class="mb-4 ..."> elements
    - Standard <ul>, <ol>, <table> elements for structured data
    """
    sections = []
    all_tables = []
    all_lists = []
    current_section = None
    
    for elem in article.descendants:
        if not isinstance(elem, Tag):
            continue
        
        # Handle headings - start new section
        if elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            # Save previous section
            if current_section and (current_section['paragraphs'] or current_section['lists'] or current_section['tables']):
                sections.append(current_section)
            
            heading_text = elem.get_text(strip=True)
            
            # Skip h1 if it's the main title
            if elem.name == 'h1':
                # Check if this is the only h1 (likely the page title)
                h1_count = len(article.find_all('h1'))
                if h1_count == 1:
                    current_section = None
                    continue
            
            current_section = {
                'level': elem.name,
                'title': heading_text,
                'paragraphs': [],
                'lists': [],
                'tables': []
            }
        
        elif current_section:
            # Paragraphs in Grokipedia are in span elements with mb-4 class
            if elem.name == 'span':
                classes = elem.get('class') or []
                if 'mb-4' in classes:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 20:
                        # Avoid duplicates - check if this exact text is already added
                        if text not in current_section['paragraphs']:
                            current_section['paragraphs'].append(text)
            
            # Lists
            elif elem.name in ['ul', 'ol']:
                # Only process top-level lists (not nested)
                if not elem.find_parent(['ul', 'ol']):
                    items = [li.get_text(strip=True) for li in elem.find_all('li', recursive=False)]
                    if items:
                        list_data = {
                            'type': elem.name,
                            'items': items
                        }
                        current_section['lists'].append(list_data)
                        
                        # Also add to global lists if unique
                        if items not in [l['items'] for l in all_lists]:
                            all_lists.append(list_data)
            
            # Tables
            elif elem.name == 'table':
                # Only process top-level tables
                if not elem.find_parent('table'):
                    table_data = extract_table(elem)
                    if table_data['rows']:
                        current_section['tables'].append(table_data)
                        
                        # Also add to global tables if unique
                        if table_data['rows'] not in [t['rows'] for t in all_tables]:
                            all_tables.append(table_data)
    
    # Don't forget the last section
    if current_section and (current_section['paragraphs'] or current_section['lists'] or current_section['tables']):
        sections.append(current_section)
    
    return sections, all_tables, all_lists


def extract_table(table_elem: Tag) -> dict:
    """
    Extract structured data from a table element.
    
    Returns:
        dict with 'headers' (list) and 'rows' (list of lists)
    """
    table_data = {
        'headers': [],
        'rows': []
    }
    
    # Try to find headers in thead
    thead = table_elem.find('thead')
    if thead:
        headers = [th.get_text(strip=True) for th in thead.find_all('th')]
        table_data['headers'] = headers
    
    # Get all rows from tbody or directly from table
    tbody = table_elem.find('tbody') or table_elem
    rows = tbody.find_all('tr')
    
    for i, row in enumerate(rows):
        cells = row.find_all(['th', 'td'])
        if not cells:
            continue
        
        cell_data = [cell.get_text(strip=True) for cell in cells]
        
        # First row might be headers if no thead
        if i == 0 and not table_data['headers']:
            if all(cell.name == 'th' for cell in cells):
                table_data['headers'] = cell_data
                continue
        
        table_data['rows'].append(cell_data)
    
    return table_data


# For testing
if __name__ == '__main__':
    async def test():
        result = await execute({
            'function': 'get_page',
            'slug': 'i_am_gloria_world_tour'
        })
        
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
        
    asyncio.run(test())