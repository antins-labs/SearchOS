"""
EPFL (École Polytechnique Fédérale de Lausanne) Access Skill

This skill provides access to EPFL's public website content including:
- Contact information (phone, email, addresses)
- Campus locations and directions
- General information pages
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import httpx


class EPFLClient:
    """Client for accessing EPFL website content."""
    
    BASE_URL = "https://www.epfl.ch"
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                follow_redirects=True,
                timeout=30.0,
                http2=True
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def fetch_page(self, path: str) -> Dict[str, Any]:
        """Fetch and parse an EPFL page."""
        client = await self._get_client()
        url = f"{self.BASE_URL}{path}" if path.startswith('/') else path
        
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            return {
                'success': True,
                'url': str(resp.url),
                'soup': soup,
                'html': resp.text
            }
        except httpx.HTTPStatusError as e:
            return {
                'success': False,
                'error': f"HTTP {e.response.status_code}",
                'url': url
            }
        except httpx.RequestError as e:
            return {
                'success': False,
                'error': f"Request error: {str(e)}",
                'url': url
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}",
                'url': url
            }
    
    def _extract_text(self, element) -> str:
        """Extract and clean text from an element."""
        if not element:
            return ""
        return ' '.join(element.get_text().split())
    
    def _extract_contact_info(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract contact information from a page."""
        info = {
            'phones': [],
            'emails': [],
            'addresses': [],
            'departments': []
        }
        
        # Get main content area
        main = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content|entry'))
        if not main:
            main = soup.body
        
        if not main:
            return info
        
        text = main.get_text()
        
        # Extract phone numbers (Swiss format)
        phone_patterns = [
            r'\+41\s*\(?\d\)?\s*\d{2}\s*\d{3}\s*\d{2}\s*\d{2}',  # +41 (0)21 693 11 11
            r'\+41\s*\d{2}\s*\d{3}\s*\d{2}\s*\d{2}',  # +41 21 693 12 34
            r'T[lé]l[:.]?\s*([\d\s\(\)]+)',  # Tel: +41 ...
            r'Phone[:.]?\s*([\d\s\(\)]+)',  # Phone: +41 ...
        ]
        
        phones_found = set()
        for pattern in phone_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                # Clean up phone number
                phone = re.sub(r'\s+', ' ', m.strip())
                if phone and len(phone) > 7:
                    phones_found.add(phone)
        
        info['phones'] = list(phones_found)
        
        # Extract emails
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
        info['emails'] = list(set(emails))
        
        # Extract Swiss addresses
        addresses = re.findall(r'CH-\d{4}\s+\w+(?:[^,\n]{0,50})?', text)
        info['addresses'] = list(set(addresses))
        
        # Extract department/service info from headings and paragraphs
        h2_elements = main.find_all(['h2', 'h3'])
        for h in h2_elements:
            heading_text = h.get_text().strip()
            next_p = h.find_next('p')
            if next_p:
                dept_info = {
                    'name': heading_text,
                    'description': self._extract_text(next_p)[:500]
                }
                
                # Look for contact details near this heading
                sibling = h.find_next_sibling()
                contact_text = ""
                while sibling and sibling.name not in ['h2', 'h3']:
                    if sibling.name in ['p', 'ul', 'ol']:
                        contact_text += sibling.get_text() + " "
                    sibling = sibling.find_next_sibling()
                    if len(contact_text) > 300:
                        break
                
                # Extract phones/emails from this section
                section_phones = re.findall(r'[\+]\d[\d\s\(\)]{8,20}', contact_text)
                section_emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', contact_text)
                
                if section_phones or section_emails:
                    dept_info['phones'] = section_phones[:3]
                    dept_info['emails'] = section_emails[:3]
                
                info['departments'].append(dept_info)
        
        return info


class EPFLExtractor:
    """Extract structured information from EPFL pages."""
    
    def __init__(self):
        self.client = EPFLClient()
    
    async def get_contact_info(self, lang: str = 'en') -> Dict[str, Any]:
        """
        Get EPFL contact information.
        
        Args:
            lang: Language code ('en', 'fr', 'de')
        
        Returns:
            Contact information including phone, email, departments
        """
        lang_paths = {
            'en': '/about/contact-en/',
            'fr': '/about/fr/contact/',
            'de': '/about/de/kontakt/'
        }
        
        path = lang_paths.get(lang, lang_paths['en'])
        
        result = await self.client.fetch_page(path)
        
        if not result['success']:
            return result
        
        soup = result['soup']
        
        # Extract basic page info
        title_elem = soup.find('title')
        h1_elem = soup.find('h1')
        
        contact_info = self.client._extract_contact_info(soup)
        
        # Extract general info sections
        sections = []
        main = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content'))
        
        if main:
            current_section = None
            for elem in main.find_all(['h2', 'h3', 'p', 'ul']):
                if elem.name in ['h2', 'h3']:
                    if current_section:
                        sections.append(current_section)
                    current_section = {
                        'heading': elem.get_text().strip(),
                        'level': elem.name,
                        'content': []
                    }
                elif current_section and elem.name == 'p':
                    text = self.client._extract_text(elem)
                    if text:
                        current_section['content'].append({'type': 'text', 'value': text})
                elif current_section and elem.name in ['ul', 'ol']:
                    items = [li.get_text().strip() for li in elem.find_all('li')]
                    if items:
                        current_section['content'].append({'type': 'list', 'value': items})
            
            if current_section:
                sections.append(current_section)
        
        return {
            'success': True,
            'url': result['url'],
            'title': title_elem.get_text().strip() if title_elem else None,
            'h1': h1_elem.get_text().strip() if h1_elem else None,
            'language': lang,
            'contact': contact_info,
            'sections': sections[:15]  # Limit sections
        }
    
    async def get_campus_location(self, campus: str = 'lausanne') -> Dict[str, Any]:
        """
        Get location and transport information for EPFL campuses.
        
        Args:
            campus: Campus name ('lausanne', 'geneva', 'fribourg', 'neuchatel', 'valais', 'all')
        
        Returns:
            Location and transport information
        """
        result = await self.client.fetch_page('/campus/visitors/coming-to-epfl/')
        
        if not result['success']:
            return result
        
        soup = result['soup']
        
        campuses = {}
        current_campus = None
        current_section = None
        
        main = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content'))
        
        if main:
            for elem in main.find_all(['h2', 'h3', 'p', 'ul', 'div']):
                text = elem.get_text().strip()
                
                # Identify campus sections
                if elem.name == 'h2':
                    if 'Main campus' in text or 'Lausanne' in text or 'Ecublens' in text:
                        current_campus = 'lausanne'
                        campuses[current_campus] = {
                            'name': 'EPFL Lausanne (Main Campus)',
                            'location': 'Ecublens, Lausanne',
                            'description': '',
                            'transport': {'metro': [], 'bus': [], 'train': [], 'walking': []},
                            'address': 'CH-1015 Lausanne, Switzerland'
                        }
                    elif 'Associated campuses' in text.lower():
                        continue
                    
                elif elem.name == 'h3':
                    if 'Fribourg' in text:
                        current_campus = 'fribourg'
                        campuses[current_campus] = {
                            'name': 'EPFL Fribourg',
                            'location': 'Fribourg, Switzerland',
                            'description': '',
                            'transport': {'bus': [], 'train': []},
                            'address': 'Passage du Cardinal 13b, 1700 Fribourg'
                        }
                    elif 'Genève' in text or 'Geneva' in text:
                        current_campus = 'geneva'
                        campuses[current_campus] = {
                            'name': 'EPFL Geneva (Campus Biotech)',
                            'location': 'Geneva, Switzerland',
                            'description': '',
                            'transport': {'bus': [], 'tram': [], 'train': []},
                            'address': 'Chemin des Mines 9, 1202 Geneva'
                        }
                    elif 'Neuchâtel' in text or 'Neuchatel' in text:
                        current_campus = 'neuchatel'
                        campuses[current_campus] = {
                            'name': 'EPFL Neuchâtel (Microcity)',
                            'location': 'Neuchâtel, Switzerland',
                            'description': '',
                            'transport': {'bus': [], 'train': [], 'funicular': []},
                            'address': 'Rue de la Maladière 71, 2000 Neuchâtel'
                        }
                    elif 'Valais' in text or 'Wallis' in text:
                        current_campus = 'valais'
                        campuses[current_campus] = {
                            'name': 'EPFL Valais Wallis',
                            'location': 'Sion, Switzerland',
                            'description': '',
                            'transport': {'bus': [], 'train': []},
                            'address': 'Rue de l\'Industrie 17, 1950 Sion'
                        }
                    else:
                        # It's a subsection heading (e.g., "By metro", "By bus")
                        current_section = text.lower()
                
                elif elem.name == 'p' and current_campus:
                    if campuses[current_campus].get('description') == '':
                        campuses[current_campus]['description'] = text[:500]
                    
                    # Identify transport type from text
                    text_lower = text.lower()
                    if any(kw in text_lower for kw in ['m1', 'm2', 'metro', 'métro']):
                        campuses[current_campus]['transport'].setdefault('metro', []).append(text)
                    elif 'bus' in text_lower or 'tl' in text_lower or 'mbc' in text_lower:
                        campuses[current_campus]['transport'].setdefault('bus', []).append(text)
                    elif 'train' in text_lower or 'sbb' in text_lower or 'rail' in text_lower:
                        campuses[current_campus]['transport'].setdefault('train', []).append(text)
                    elif 'walking' in text_lower or 'minutes' in text_lower and 'km' in text_lower:
                        campuses[current_campus]['transport'].setdefault('walking', []).append(text)
                
                elif elem.name == 'ul' and current_campus:
                    items = [li.get_text().strip() for li in elem.find_all('li')]
                    if current_section:
                        section_type = current_section.lower()
                        if 'metro' in section_type or 'métro' in section_type:
                            campuses[current_campus]['transport'].setdefault('metro', []).extend(items)
                        elif 'bus' in section_type:
                            campuses[current_campus]['transport'].setdefault('bus', []).extend(items)
                        elif 'train' in section_type:
                            campuses[current_campus]['transport'].setdefault('train', []).extend(items)
                        elif 'tram' in section_type:
                            campuses[current_campus]['transport'].setdefault('tram', []).extend(items)
        
        # Filter by campus if specified
        if campus != 'all':
            campus_key = campus.lower()
            if campus_key in campuses:
                campuses = {campus_key: campuses[campus_key]}
            elif campus_key == 'geneva' and 'geneva' in campuses:
                campuses = {'geneva': campuses['geneva']}
        
        return {
            'success': True,
            'url': result['url'],
            'campuses': campuses
        }
    
    async def get_page_content(self, path: str) -> Dict[str, Any]:
        """
        Get content from a specific EPFL page.
        
        Args:
            path: URL path (e.g., '/about/en/about/')
        
        Returns:
            Page content with structured data
        """
        # Ensure path starts with /
        if not path.startswith('/'):
            path = '/' + path
        
        result = await self.client.fetch_page(path)
        
        if not result['success']:
            return result
        
        soup = result['soup']
        
        # Extract page info
        title_elem = soup.find('title')
        h1_elem = soup.find('h1')
        description = soup.find('meta', attrs={'name': 'description'})
        
        # Extract main content
        main = soup.find('main') or soup.find('article') or soup.find('div', class_=re.compile(r'content|entry'))
        
        content = {
            'paragraphs': [],
            'headings': [],
            'lists': [],
            'links': []
        }
        
        if main:
            # Extract headings
            for level in ['h1', 'h2', 'h3']:
                for h in main.find_all(level):
                    text = h.get_text().strip()
                    if text:
                        content['headings'].append({
                            'level': level,
                            'text': text
                        })
            
            # Extract paragraphs
            for p in main.find_all('p'):
                text = self.client._extract_text(p)
                if text and len(text) > 20:
                    content['paragraphs'].append(text)
            
            # Extract lists
            for lst in main.find_all(['ul', 'ol']):
                items = [li.get_text().strip() for li in lst.find_all('li')]
                if items:
                    content['lists'].append(items)
            
            # Extract links
            for a in main.find_all('a', href=True):
                text = a.get_text().strip()
                href = a['href']
                if text and href and not href.startswith('#') and not href.startswith('javascript:'):
                    content['links'].append({
                        'text': text,
                        'url': href
                    })
        
        # Extract contact info
        contact = self.client._extract_contact_info(soup)
        
        return {
            'success': True,
            'url': result['url'],
            'title': title_elem.get_text().strip() if title_elem else None,
            'h1': h1_elem.get_text().strip() if h1_elem else None,
            'description': description['content'] if description else None,
            'content': content,
            'contact': contact if (contact['phones'] or contact['emails'] or contact['addresses']) else None
        }
    
    async def search_pages(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """
        Search EPFL pages using the site's search functionality.
        
        Note: EPFL's built-in search has limitations. This function provides
        a curated list of common pages along with any search results found.
        
        Args:
            query: Search query
            limit: Maximum number of results
        
        Returns:
            Search results including curated popular pages
        """
        client = await self.client._get_client()
        
        results = []
        query_lower = query.lower()
        
        try:
            # Try the main site search with POST to avoid redirects
            search_url = f"{self.client.BASE_URL}/en/"
            params = {'s': query}
            
            resp = await client.get(search_url, params=params)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Extract search results from the page
            # EPFL uses article elements for results
            main = soup.find('main', class_='site-main')
            
            if main:
                articles = main.find_all('article')
                for article in articles:
                    title_elem = article.find(['h2', 'h3'], class_=re.compile(r'entry-title'))
                    link_elem = title_elem.find('a', href=True) if title_elem else None
                    snippet_elem = article.find('div', class_=re.compile(r'entry-summary|entry-content'))
                    
                    if title_elem and link_elem:
                        result = {
                            'title': title_elem.get_text().strip(),
                            'url': link_elem['href'],
                            'snippet': snippet_elem.get_text().strip()[:200] if snippet_elem else None,
                            'type': 'search_result'
                        }
                        results.append(result)
                        
                        if len(results) >= limit:
                            break
            
            # If no results found, provide curated popular pages matching the query
            if not results:
                # Curated list of popular EPFL pages
                popular_pages = [
                    {'title': 'About EPFL', 'url': '/about/en/about/', 'keywords': ['about', 'epfl', 'overview', 'mission']},
                    {'title': 'Education', 'url': '/education/', 'keywords': ['education', 'study', 'degree', 'bachelor', 'master', 'phd', 'student']},
                    {'title': 'Research', 'url': '/research/', 'keywords': ['research', 'lab', 'laboratory', 'science', 'innovation']},
                    {'title': 'Innovation', 'url': '/innovation/', 'keywords': ['innovation', 'startup', 'industry', 'transfer', 'technology']},
                    {'title': 'Campus', 'url': '/campus/', 'keywords': ['campus', 'facilities', 'services', 'life']},
                    {'title': 'Schools', 'url': '/schools/', 'keywords': ['school', 'faculty', 'department', 'institute']},
                    {'title': 'Labs Directory', 'url': '/labs/', 'keywords': ['lab', 'laboratory', 'research', 'group']},
                    {'title': 'Contact', 'url': '/about/contact-en/', 'keywords': ['contact', 'phone', 'email', 'address']},
                    {'title': 'Getting to EPFL', 'url': '/campus/visitors/coming-to-epfl/', 'keywords': ['location', 'direction', 'transport', 'metro', 'bus', 'train', 'map', 'address', 'campus']},
                    {'title': 'Working at EPFL', 'url': '/about/working-at-epfl/', 'keywords': ['job', 'career', 'employment', 'work', 'position']},
                    {'title': 'Admissions', 'url': '/education/admissions/', 'keywords': ['admission', 'apply', 'application', 'enrollment']},
                    {'title': 'Student Services', 'url': '/campus/services/students/', 'keywords': ['student', 'service', 'support', 'help']},
                    {'title': 'Library', 'url': '/campus/library/', 'keywords': ['library', 'book', 'resource', 'study']},
                    {'title': 'News', 'url': '/news/', 'keywords': ['news', 'article', 'press', 'media']},
                    {'title': 'Events', 'url': '/events/', 'keywords': ['event', 'conference', 'seminar', 'workshop']},
                ]
                
                # Filter popular pages by query keywords
                query_words = set(query_lower.split())
                for page in popular_pages:
                    page_words = set(page['keywords'])
                    # Check if any query word matches any keyword
                    if query_words & page_words or any(word in query_lower for word in page['keywords']):
                        results.append({
                            'title': page['title'],
                            'url': f"{self.client.BASE_URL}{page['url']}",
                            'snippet': f"Related to: {', '.join(page['keywords'][:5])}",
                            'type': 'curated'
                        })
                        if len(results) >= limit:
                            break
                
                # If still no matches, return top popular pages
                if not results:
                    for page in popular_pages[:limit]:
                        results.append({
                            'title': page['title'],
                            'url': f"{self.client.BASE_URL}{page['url']}",
                            'snippet': f"Popular page - related to: {', '.join(page['keywords'][:5])}",
                            'type': 'curated'
                        })
            
            return {
                'success': True,
                'query': query,
                'results': results[:limit],
                'total': len(results[:limit]),
                'note': 'EPFL\'s built-in search has limitations. Results include curated popular pages when search yields no matches.'
            }
            
        except httpx.HTTPStatusError as e:
            # Provide curated results even on error
            curated = [
                {'title': 'About EPFL', 'url': f"{self.client.BASE_URL}/about/en/about/", 'type': 'curated'},
                {'title': 'Education', 'url': f"{self.client.BASE_URL}/education/", 'type': 'curated'},
                {'title': 'Research', 'url': f"{self.client.BASE_URL}/research/", 'type': 'curated'},
                {'title': 'Campus', 'url': f"{self.client.BASE_URL}/campus/", 'type': 'curated'},
                {'title': 'Contact', 'url': f"{self.client.BASE_URL}/about/contact-en/", 'type': 'curated'},
            ]
            return {
                'success': True,
                'query': query,
                'results': curated[:limit],
                'total': len(curated[:limit]),
                'note': 'Search endpoint returned error; showing popular pages instead.'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'error_type': 'execution',
                'query': query,
                'results': []
            }

    async def close(self):
        """Close the HTTP client."""
        await self.client.close()


# Global extractor instance
_extractor: Optional[EPFLExtractor] = None


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute EPFL access skill operations.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_contact_info', 'get_campus_location', 'get_page_content', 'search_pages'
            - Additional parameters specific to each function
        ctx: Context (unused)
    
    Returns:
        Dictionary with operation results
    """
    global _extractor
    
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'error_type': 'validation'
        }
    
    # Initialize extractor
    if _extractor is None:
        _extractor = EPFLExtractor()
    
    try:
        if function == 'get_contact_info':
            lang = params.get('lang', 'en')
            result = await _extractor.get_contact_info(lang=lang)
            return result
        
        elif function == 'get_campus_location':
            campus = params.get('campus', 'all')
            result = await _extractor.get_campus_location(campus=campus)
            return result
        
        elif function == 'get_page_content':
            path = params.get('path')
            if not path:
                return {
                    'success': False,
                    'error': 'Missing required parameter: path',
                    'error_type': 'validation'
                }
            result = await _extractor.get_page_content(path=path)
            return result
        
        elif function == 'search_pages':
            query = params.get('query')
            if not query:
                return {
                    'success': False,
                    'error': 'Missing required parameter: query',
                    'error_type': 'validation'
                }
            limit = params.get('limit', 10)
            result = await _extractor.search_pages(query=query, limit=limit)
            return result
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'error_type': 'validation',
                'available_functions': ['get_contact_info', 'get_campus_location', 'get_page_content', 'search_pages']
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': 'execution'
        }


# Cleanup function for graceful shutdown
async def cleanup():
    """Cleanup resources."""
    global _extractor
    if _extractor:
        await _extractor.close()
        _extractor = None