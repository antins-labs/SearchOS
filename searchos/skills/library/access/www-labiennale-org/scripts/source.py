"""
La Biennale di Venezia Film Festival Extractor

Extracts structured data from the Venice Film Festival website including:
- Festival lineup sections (Venezia, Orizzonti, Out of Competition, etc.)
- Film listings within each section
- Detailed film information (cast, crew, synopsis, etc.)
"""

import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from typing import Dict, List, Any, Optional


class LaBiennaleExtractor:
    """Extract film festival data from La Biennale di Venezia website"""
    
    BASE_URL = "https://www.labiennale.org"
    
    async def fetch_page(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Fetch HTML from a URL"""
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception as e:
            return None
    
    def parse_lineup_page(self, html: str, url: str) -> Dict[str, Any]:
        """Parse the main lineup page to get festival sections"""
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            'url': url,
            'title': '',
            'year': '',
            'sections': [],
            'success': True,
            'error': None
        }
        
        # Extract year from URL
        year_match = re.search(r'/cinema/(\d{4})/', url)
        if year_match:
            result['year'] = year_match.group(1)
        
        # Get page title
        title_tag = soup.find('title')
        if title_tag:
            result['title'] = title_tag.get_text().strip()
        
        # Find all section articles
        articles = soup.find_all('article', class_='node-teaser')
        
        for article in articles:
            section = {}
            
            # Get the main link
            link = article.find('a', href=True)
            if link:
                href = link.get('href', '')
                section['url'] = urljoin(self.BASE_URL, href)
                section['path'] = href
                
                # Get title from the link text
                link_text = link.get_text().strip()
                # The format is usually "Read more\n\nTITLE\n\nDescription"
                lines = [l.strip() for l in link_text.split('\n') if l.strip()]
                
                if len(lines) >= 1:
                    # Skip "Read more" if present
                    title_idx = 0
                    if 'Read more' in lines[0]:
                        title_idx = 1 if len(lines) > 1 else 0
                    
                    if title_idx < len(lines):
                        section['title'] = lines[title_idx]
                
                # Get description from lb-description div
                desc_div = article.find('div', class_='lb-description')
                if desc_div:
                    section['description'] = ' '.join(desc_div.get_text().split())
            
            if section.get('title') and section.get('url'):
                result['sections'].append(section)
        
        return result
    
    def parse_film_entry(self, article) -> Optional[Dict[str, Any]]:
        """Parse a single film entry from a section page"""
        film = {}
        
        # Find the main link
        link = article.find('a', class_='lb-entry-link')
        if not link:
            return None
        
        href = link.get('href', '')
        if not href:
            return None
        
        film['url'] = urljoin(self.BASE_URL, href)
        film['path'] = href
        
        # Get title
        title_div = link.find('div', class_='lb-item-title')
        if title_div:
            film['title'] = title_div.get_text().strip()
        else:
            return None
        
        # Get description (contains director, cast, country, duration)
        desc_div = link.find('div', class_='lb-description')
        if desc_div:
            desc_text = desc_div.get_text()
            
            # Extract director - format: "Director \r\n  <strong>Name</strong>"
            director_match = re.search(r'Director\s+(.+?)(?:Main Cast|$)', desc_text, re.DOTALL)
            if director_match:
                director = director_match.group(1).strip()
                director = re.sub(r'\s+', ' ', director)
                film['director'] = director
            
            # Extract main cast - format: "Main Cast \r\n  Names / Country / Duration"
            cast_match = re.search(r'Main Cast\s+(.+?)(?:/|$)', desc_text, re.DOTALL)
            if cast_match:
                cast = cast_match.group(1).strip()
                cast = re.sub(r'\s+', ' ', cast)
                film['main_cast'] = cast
            
            # Extract country and duration (format: / Country / 123')
            parts = desc_text.split('/')
            if len(parts) >= 2:
                # Last part is usually duration
                dur_text = parts[-1].strip()
                duration_match = re.search(r"(\d+\s*'?)", dur_text)
                if duration_match:
                    film['duration'] = duration_match.group(1)
                
                # Second to last might be country (but not if cast info is included)
                if len(parts) >= 3:
                    country_text = parts[-2].strip()
                    # Only use if it looks like a country (short text, possibly with comma)
                    if len(country_text) < 50 and not 'Cast' in country_text:
                        film['country'] = ' '.join(country_text.split())[:50]
        
        # Get thumbnail image
        img = link.find('img', class_='lb-media')
        if img:
            film['thumbnail'] = img.get('src', '')
        
        return film
    
    def parse_section_page(self, html: str, url: str) -> Dict[str, Any]:
        """Parse a section page to get list of films"""
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            'url': url,
            'title': '',
            'section': '',
            'year': '',
            'films': [],
            'success': True,
            'error': None
        }
        
        # Extract year from URL
        year_match = re.search(r'/cinema/(\d{4})/', url)
        if year_match:
            result['year'] = year_match.group(1)
        
        # Get page title
        title_tag = soup.find('title')
        if title_tag:
            result['title'] = title_tag.get_text().strip()
        
        # Get section name from h1
        h1 = soup.find('h1', class_='lb-hero-title') or soup.find('h1')
        if h1:
            result['section'] = h1.get_text().strip()
        
        # Find all film articles
        film_articles = soup.find_all('article', class_='node-film')
        
        for article in film_articles:
            film = self.parse_film_entry(article)
            if film and film.get('title'):
                result['films'].append(film)
        
        return result
    
    def parse_film_page(self, html: str, url: str) -> Dict[str, Any]:
        """Parse individual film page for detailed information"""
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            'url': url,
            'title': '',
            'section': '',
            'year': '',
            'director': '',
            'production': '',
            'running_time': '',
            'language': '',
            'country': '',
            'main_cast': '',
            'screenplay': '',
            'cinematographer': '',
            'editor': '',
            'production_designer': '',
            'costume_designer': '',
            'music': '',
            'sound': '',
            'visual_effects': '',
            'synopsis': '',
            'success': True,
            'error': None
        }
        
        # Extract year from URL
        year_match = re.search(r'/cinema/(\d{4})/', url)
        if year_match:
            result['year'] = year_match.group(1)
        
        # Get film title from h1
        h1 = soup.find('h1', class_='lb-page-title')
        if h1:
            result['title'] = h1.get_text().strip()
        
        # Get section from description div
        desc_div = soup.find('div', class_='lb-description')
        if desc_div:
            result['section'] = desc_div.get_text().strip()
        
        # Parse the film data table
        table = soup.find('table', class_='lb-dati-film')
        if table:
            rows = table.find_all('tr')
            for row in rows:
                th = row.find('th')
                td = row.find('td')
                
                if th and td:
                    label = th.get_text().strip().rstrip(':').lower()
                    value = td.get_text().strip()
                    
                    # Map labels to fields
                    if 'director' in label or 'regia' in label:
                        result['director'] = value
                    elif 'production' in label and 'designer' not in label:
                        result['production'] = value
                    elif ('running time' in label or 'duration' in label or 
                          'durata' in label or 'duración' in label):
                        result['running_time'] = value
                    elif 'language' in label or 'lingua' in label or 'idioma' in label:
                        result['language'] = value
                    elif 'country' in label or 'paes' in label or 'país' in label:
                        result['country'] = value
                    elif 'cast' in label or 'interpreti' in label:
                        result['main_cast'] = value
                    elif 'screenplay' in label or 'sceneggiatura' in label:
                        result['screenplay'] = value
                    elif ('cinematographer' in label or 'photography' in label or 
                          'fotografia' in label):
                        result['cinematographer'] = value
                    elif 'editor' in label or 'montaggio' in label:
                        result['editor'] = value
                    elif ('production designer' in label or 'scenograf' in label):
                        result['production_designer'] = value
                    elif 'costume' in label:
                        result['costume_designer'] = value
                    elif 'music' in label or 'musiche' in label:
                        result['music'] = value
                    elif 'sound' in label or 'sonoro' in label:
                        result['sound'] = value
                    elif ('visual effects' in label or 'effetti' in label):
                        result['visual_effects'] = value
        
        # Look for synopsis
        content_div = soup.find('div', class_='lb-page-content')
        if content_div:
            paragraphs = content_div.find_all('p')
            if paragraphs:
                synopsis_parts = []
                for p in paragraphs:
                    text = p.get_text().strip()
                    if text and len(text) > 50:  # Filter out short snippets
                        synopsis_parts.append(text)
                if synopsis_parts:
                    result['synopsis'] = ' '.join(synopsis_parts)[:1000]
        
        return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute function for the La Biennale Film Festival extractor.
    
    Parameters:
    - function: The action to perform
      - 'get_lineup': Get festival lineup sections
      - 'get_section': Get films in a section
      - 'get_film': Get detailed film information
      - 'search_films': Search for films by title
    
    Additional parameters depend on the function:
    - get_lineup: year (required)
    - get_section: url (required) or section_path and year
    - get_film: url (required)
    - search_films: query (required), year (optional)
    """
    
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'error_type': 'validation'
        }
    
    extractor = LaBiennaleExtractor()
    
    async with aiohttp.ClientSession() as session:
        if function == 'get_lineup':
            year = params.get('year')
            if not year:
                return {
                    'success': False,
                    'error': 'Missing required parameter: year',
                    'error_type': 'validation'
                }
            
            url = f"https://www.labiennale.org/en/cinema/{year}/lineup"
            html = await extractor.fetch_page(session, url)
            
            if not html:
                return {
                    'success': False,
                    'error': f'Failed to fetch lineup page for year {year}',
                    'error_type': 'network',
                    'url': url
                }
            
            return extractor.parse_lineup_page(html, url)
        
        elif function == 'get_section':
            url = params.get('url')
            
            if not url:
                # Build URL from path and year
                section_path = params.get('section_path')
                year = params.get('year', '2019')
                
                if section_path:
                    url = f"https://www.labiennale.org/en/cinema/{year}/{section_path}"
                else:
                    return {
                        'success': False,
                        'error': 'Missing required parameter: url or section_path',
                        'error_type': 'validation'
                    }
            
            html = await extractor.fetch_page(session, url)
            
            if not html:
                return {
                    'success': False,
                    'error': f'Failed to fetch section page: {url}',
                    'error_type': 'network',
                    'url': url
                }
            
            return extractor.parse_section_page(html, url)
        
        elif function == 'get_film':
            url = params.get('url')
            
            if not url:
                return {
                    'success': False,
                    'error': 'Missing required parameter: url',
                    'error_type': 'validation'
                }
            
            html = await extractor.fetch_page(session, url)
            
            if not html:
                return {
                    'success': False,
                    'error': f'Failed to fetch film page: {url}',
                    'error_type': 'network',
                    'url': url
                }
            
            return extractor.parse_film_page(html, url)
        
        elif function == 'search_films':
            query = params.get('query')
            year = params.get('year', '2019')
            
            if not query:
                return {
                    'success': False,
                    'error': 'Missing required parameter: query',
                    'error_type': 'validation'
                }
            
            # Get lineup first
            lineup_url = f"https://www.labiennale.org/en/cinema/{year}/lineup"
            lineup_html = await extractor.fetch_page(session, lineup_url)
            
            if not lineup_html:
                return {
                    'success': False,
                    'error': f'Failed to fetch lineup for year {year}',
                    'error_type': 'network',
                    'url': lineup_url
                }
            
            lineup = extractor.parse_lineup_page(lineup_html, lineup_url)
            
            # Search through all sections
            results = []
            query_lower = query.lower()
            
            for section in lineup.get('sections', []):
                section_url = section.get('url')
                if not section_url:
                    continue
                
                section_html = await extractor.fetch_page(session, section_url)
                if not section_html:
                    continue
                
                section_data = extractor.parse_section_page(section_html, section_url)
                
                # Filter films matching query
                for film in section_data.get('films', []):
                    title = film.get('title', '').lower()
                    director = film.get('director', '').lower()
                    
                    # Check if query matches title or director
                    score = 0
                    if query_lower in title:
                        score = 100 if title == query_lower else (80 if title.startswith(query_lower) else 60)
                    elif query_lower in director:
                        score = 50
                    
                    if score > 0:
                        film_copy = film.copy()
                        film_copy['match_score'] = score
                        film_copy['section_title'] = section.get('title', '')
                        results.append(film_copy)
            
            # Sort by score
            results.sort(key=lambda x: x.get('match_score', 0), reverse=True)
            
            return {
                'success': True,
                'query': query,
                'year': year,
                'total_results': len(results),
                'films': results[:50],  # Return top 50
                'error': None
            }
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'error_type': 'validation'
            }