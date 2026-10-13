"""
UChicago Journals Access Skill

Access University of Chicago Press journal articles and table of contents via Crossref API.
The site is protected by Cloudflare Turnstile, so we use Crossref as a metadata source.

Supported functions:
- get_article_metadata: Get full metadata for an article by DOI
- get_toc_current: Get current issue's table of contents for a journal
- get_toc_issue: Get specific issue's table of contents
- get_references: Get references cited by an article
- search_articles: Search for articles in a journal (limited to recent works)
"""

import asyncio
import aiohttp
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs
import re


# Journal code to ISSN mapping for UChicago Press journals
JOURNAL_MAP = {
    'ajs': {'name': 'American Journal of Sociology', 'issn': '0002-9602'},
    'jpe': {'name': 'Journal of Political Economy', 'issn': '0022-3808'},
    'jols': {'name': 'The Journal of Law and Economics', 'issn': '0022-2186'},
    'jole': {'name': 'Journal of Labor Economics', 'issn': '0734-306X'},
    'an': {'name': 'The American Naturalist', 'issn': '0003-0147'},
    'pt': {'name': 'Physiological and Biochemical Zoology', 'issn': '1522-2152'},
    'ijal': {'name': 'International Journal of American Linguistics', 'issn': '0020-7071'},
    'ajsarch': {'name': 'American Journal of Archaeology', 'issn': '0002-9114'},
    'jop': {'name': 'The Journal of Politics', 'issn': '0022-3816'},
    'jacr': {'name': 'Journal of the Association for Consumer Research', 'issn': '2378-1815'},
    'jaere': {'name': 'Journal of the Association of Environmental and Resource Economists', 'issn': '2333-5955'},
    'mre': {'name': 'Marine Resource Economics', 'issn': '0738-1360'},
    'mp': {'name': 'Modern Philology', 'issn': '0026-8232'},
    'jhc': {'name': 'Journal of Human Capital', 'issn': '1932-8575'},
    'fws': {'name': 'Freshwater Science', 'issn': '2161-9549'},
    'reep': {'name': 'Review of Environmental Economics and Policy', 'issn': '1750-6816'},
    'ca': {'name': 'Current Anthropology', 'issn': '0011-3204'},
    'esj': {'name': 'The Elementary School Journal', 'issn': '0013-5984'},
}

# UChicago Press DOI prefix
UCHICAGO_PREFIX = '10.1086'


class UChicagoJournalsClient:
    """Client for accessing UChicago Press journal metadata via Crossref API."""
    
    def __init__(self):
        self.base_url = 'https://api.crossref.org'
        self.headers = {
            'User-Agent': 'SearchOS-UChicagoJournals/1.0 (mailto:contact@example.com)',
            'Accept': 'application/json'
        }
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def _get(self, url: str, params: Optional[Dict] = None) -> Dict:
        """Make GET request to Crossref API."""
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    return {'error': 'Not found', 'status_code': 404}
                else:
                    return {'error': f'HTTP {response.status}', 'status_code': response.status}
        except asyncio.TimeoutError:
            return {'error': 'Request timeout'}
        except Exception as e:
            return {'error': str(e)}
    
    def _parse_article(self, item: Dict) -> Dict:
        """Parse article metadata from Crossref item."""
        authors = []
        for author in item.get('author', []):
            author_data = {
                'given': author.get('given', ''),
                'family': author.get('family', ''),
                'sequence': author.get('sequence', '')
            }
            if author.get('affiliation'):
                author_data['affiliation'] = [aff.get('name', '') for aff in author.get('affiliation', [])]
            authors.append(author_data)
        
        # Clean title (remove HTML tags)
        title_raw = item.get('title', [''])[0] if item.get('title') else None
        title = re.sub(r'<[^>]+>', '', title_raw) if title_raw else None
        title = title.strip() if title else None
        
        # Clean container title
        container_raw = item.get('container-title', [''])[0] if item.get('container-title') else None
        container = container_raw.strip() if container_raw else None
        
        return {
            'doi': item.get('DOI'),
            'title': title,
            'authors': authors,
            'journal': container,
            'issn': item.get('ISSN', []),
            'volume': item.get('volume'),
            'issue': item.get('issue'),
            'page': item.get('page'),
            'published_date': item.get('published-print', {}).get('date-parts', [[None]])[0],
            'type': item.get('type'),
            'publisher': item.get('publisher'),
            'url': item.get('URL'),
            'abstract': item.get('abstract'),
            'is_referenced_by_count': item.get('is-referenced-by-count', 0),
            'reference_count': item.get('reference-count', 0),
        }
    
    async def get_article_metadata(self, doi: str) -> Dict[str, Any]:
        """
        Get full metadata for an article by DOI.
        
        Args:
            doi: Digital Object Identifier (e.g., '10.1086/739568')
        
        Returns:
            Dictionary with article metadata or error
        """
        # Normalize DOI (remove 'doi:' prefix if present)
        doi = doi.strip().lower()
        if doi.startswith('doi:'):
            doi = doi[4:].strip()
        
        # Validate DOI
        if not doi.startswith(UCHICAGO_PREFIX):
            # Still try to fetch from Crossref, but note it may not be UChicago
            pass
        
        url = f'{self.base_url}/works/{doi}'
        data = await self._get(url)
        
        if 'error' in data:
            return {'success': False, 'error': data['error'], 'doi': doi}
        
        message = data.get('message', {})
        article = self._parse_article(message)
        
        # Get references if available
        references = []
        for ref in message.get('reference', []):
            ref_data = {'key': ref.get('key')}
            if ref.get('DOI'):
                ref_data['doi'] = ref['DOI']
            if ref.get('year'):
                ref_data['year'] = ref['year']
            if ref.get('article-title'):
                ref_data['article_title'] = ref['article-title']
            if ref.get('author'):
                ref_data['author'] = ref['author']
            if ref.get('journal-title'):
                ref_data['journal_title'] = ref['journal-title']
            references.append(ref_data)
        
        article['references'] = references
        
        return {'success': True, 'article': article}
    
    async def get_toc_current(self, journal_code: str, limit: int = 50) -> Dict[str, Any]:
        """
        Get current issue's table of contents for a journal.
        
        Args:
            journal_code: Journal code (e.g., 'ajs' for American Journal of Sociology)
            limit: Maximum number of articles to return (default 50)
        
        Returns:
            Dictionary with issue information and list of articles
        """
        # Get journal info
        journal_info = JOURNAL_MAP.get(journal_code.lower())
        if not journal_info:
            # Try to look up journal by code
            return {
                'success': False,
                'error': f'Unknown journal code: {journal_code}. Known codes: {", ".join(JOURNAL_MAP.keys())}'
            }
        
        issn = journal_info['issn']
        
        # Get recent works from this journal
        url = f'{self.base_url}/works'
        params = {
            'filter': f'issn:{issn}',
            'rows': limit,
            'sort': 'published',
            'order': 'desc'
        }
        
        data = await self._get(url, params)
        
        if 'error' in data:
            return {'success': False, 'error': data['error'], 'journal_code': journal_code}
        
        message = data.get('message', {})
        if isinstance(message, list):
            return {'success': False, 'error': 'Unexpected response format from Crossref'}
        
        items = message.get('items', [])
        
        # Group by volume/issue
        issues = {}
        for item in items:
            vol = item.get('volume') or 'N/A'
            issue_num = item.get('issue') or 'N/A'
            key = f'Volume {vol}, Issue {issue_num}'
            
            if key not in issues:
                issues[key] = {
                    'volume': vol,
                    'issue': issue_num,
                    'articles': []
                }
            
            article = self._parse_article(item)
            issues[key]['articles'].append(article)
        
        # The first issue is the most recent
        issue_keys = list(issues.keys())
        current_issue = issues[issue_keys[0]] if issue_keys else None
        
        return {
            'success': True,
            'journal': {
                'code': journal_code,
                'name': journal_info['name'],
                'issn': issn
            },
            'current_issue': current_issue,
            'all_issues': [
                {
                    'volume': issues[k]['volume'],
                    'issue': issues[k]['issue'],
                    'article_count': len(issues[k]['articles'])
                }
                for k in issue_keys
            ]
        }
    
    async def get_toc_issue(self, journal_code: str, volume: str, issue: str) -> Dict[str, Any]:
        """
        Get table of contents for a specific issue.
        
        Args:
            journal_code: Journal code (e.g., 'ajs')
            volume: Volume number (e.g., '131')
            issue: Issue number (e.g., '4')
        
        Returns:
            Dictionary with issue information and list of articles
        """
        journal_info = JOURNAL_MAP.get(journal_code.lower())
        if not journal_info:
            return {
                'success': False,
                'error': f'Unknown journal code: {journal_code}. Known codes: {", ".join(JOURNAL_MAP.keys())}'
            }
        
        issn = journal_info['issn']
        
        # Get works from this journal
        # Note: Crossref doesn't support volume filter directly, so we get more and filter manually
        url = f'{self.base_url}/works'
        params = {
            'filter': f'issn:{issn}',
            'rows': 500,  # Get enough to find the issue
            'sort': 'published',
            'order': 'desc'
        }
        
        data = await self._get(url, params)
        
        if 'error' in data:
            return {'success': False, 'error': data['error']}
        
        message = data.get('message', {})
        if isinstance(message, list):
            return {'success': False, 'error': 'Unexpected response format from Crossref'}
        
        items = message.get('items', [])
        
        # Filter for specific volume and issue
        articles = []
        for item in items:
            if item.get('volume') == volume and item.get('issue') == issue:
                article = self._parse_article(item)
                articles.append(article)
        
        # Sort by page number if available
        def page_sort_key(article):
            page = article.get('page', '')
            if page:
                # Extract first page number
                match = re.match(r'(\d+)', page)
                if match:
                    return int(match.group(1))
            return 999999
        
        articles.sort(key=page_sort_key)
        
        if not articles:
            return {
                'success': False,
                'error': f'No articles found for Volume {volume}, Issue {issue} in {journal_info["name"]}. '
                        f'This issue may not exist or may not be indexed in Crossref yet.',
                'journal': journal_info['name'],
                'volume': volume,
                'issue': issue
            }
        
        return {
            'success': True,
            'journal': {
                'code': journal_code,
                'name': journal_info['name'],
                'issn': issn
            },
            'issue': {
                'volume': volume,
                'issue': issue,
                'article_count': len(articles)
            },
            'articles': articles
        }
    
    async def get_references(self, doi: str, limit: int = 100) -> Dict[str, Any]:
        """
        Get references cited by an article.
        
        Args:
            doi: Digital Object Identifier
            limit: Maximum number of references to return
        
        Returns:
            Dictionary with list of references
        """
        # Normalize DOI
        doi = doi.strip().lower()
        if doi.startswith('doi:'):
            doi = doi[4:].strip()
        
        url = f'{self.base_url}/works/{doi}'
        data = await self._get(url)
        
        if 'error' in data:
            return {'success': False, 'error': data['error'], 'doi': doi}
        
        message = data.get('message', {})
        
        references = []
        for i, ref in enumerate(message.get('reference', [])[:limit]):
            ref_data = {
                'index': i + 1,
                'key': ref.get('key'),
            }
            if ref.get('DOI'):
                ref_data['doi'] = ref['DOI']
            if ref.get('year'):
                ref_data['year'] = ref['year']
            if ref.get('article-title'):
                ref_data['article_title'] = ref['article-title']
            if ref.get('author'):
                ref_data['author'] = ref['author']
            if ref.get('journal-title'):
                ref_data['journal_title'] = ref['journal-title']
            if ref.get('volume'):
                ref_data['volume'] = ref['volume']
            if ref.get('page'):
                ref_data['page'] = ref['page']
            if ref.get('first-page'):
                ref_data['first_page'] = ref['first-page']
            references.append(ref_data)
        
        return {
            'success': True,
            'doi': doi,
            'title': message.get('title', [''])[0] if message.get('title') else None,
            'reference_count': message.get('reference-count', 0),
            'references_returned': len(references),
            'references': references
        }
    
    async def search_articles(self, journal_code: str, query: Optional[str] = None, 
                             limit: int = 20) -> Dict[str, Any]:
        """
        Search for articles in a journal (limited to recent works).
        
        Note: Crossref doesn't provide full-text search, so this returns recent articles.
        Use query parameter to filter results.
        
        Args:
            journal_code: Journal code (e.g., 'ajs')
            query: Optional search query (filters title)
            limit: Maximum number of articles to return
        
        Returns:
            Dictionary with list of articles
        """
        journal_info = JOURNAL_MAP.get(journal_code.lower())
        if not journal_info:
            return {
                'success': False,
                'error': f'Unknown journal code: {journal_code}. Known codes: {", ".join(JOURNAL_MAP.keys())}'
            }
        
        issn = journal_info['issn']
        
        url = f'{self.base_url}/works'
        params = {
            'filter': f'issn:{issn},type:journal-article',
            'rows': min(limit * 3, 100),  # Get more to allow for filtering
            'sort': 'published',
            'order': 'desc'
        }
        
        data = await self._get(url, params)
        
        if 'error' in data:
            return {'success': False, 'error': data['error']}
        
        message = data.get('message', {})
        if isinstance(message, list):
            return {'success': False, 'error': 'Unexpected response format from Crossref'}
        
        items = message.get('items', [])
        
        articles = []
        for item in items:
            article = self._parse_article(item)
            
            # Filter by query if provided
            if query:
                query_lower = query.lower()
                title = article.get('title', '') or ''
                if query_lower not in title.lower():
                    # Also check author names
                    author_match = any(
                        query_lower in f"{a.get('given', '')} {a.get('family', '')}".lower()
                        for a in article.get('authors', [])
                    )
                    if not author_match:
                        continue
            
            articles.append(article)
            
            if len(articles) >= limit:
                break
        
        return {
            'success': True,
            'journal': {
                'code': journal_code,
                'name': journal_info['name'],
                'issn': issn
            },
            'query': query,
            'total_results': len(articles),
            'articles': articles
        }
    
    async def list_journals(self) -> Dict[str, Any]:
        """
        List all supported UChicago Press journals.
        
        Returns:
            Dictionary with list of journals
        """
        journals = []
        for code, info in JOURNAL_MAP.items():
            journals.append({
                'code': code,
                'name': info['name'],
                'issn': info['issn']
            })
        
        return {
            'success': True,
            'journals': sorted(journals, key=lambda x: x['name']),
            'count': len(journals)
        }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute UChicago Journals skill function.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with 'success' flag and result data or error message
    """
    function = params.get('function')
    if not function:
        return {'success': False, 'error': 'Missing required parameter: function'}
    
    async with UChicagoJournalsClient() as client:
        if function == 'get_article_metadata':
            doi = params.get('doi')
            if not doi:
                return {'success': False, 'error': 'Missing required parameter: doi'}
            return await client.get_article_metadata(doi)
        
        elif function == 'get_toc_current':
            journal_code = params.get('journal_code')
            if not journal_code:
                return {'success': False, 'error': 'Missing required parameter: journal_code'}
            limit = params.get('limit', 50)
            return await client.get_toc_current(journal_code, limit)
        
        elif function == 'get_toc_issue':
            journal_code = params.get('journal_code')
            volume = params.get('volume')
            issue = params.get('issue')
            if not all([journal_code, volume, issue]):
                return {
                    'success': False,
                    'error': 'Missing required parameters. Required: journal_code, volume, issue'
                }
            return await client.get_toc_issue(journal_code, volume, issue)
        
        elif function == 'get_references':
            doi = params.get('doi')
            if not doi:
                return {'success': False, 'error': 'Missing required parameter: doi'}
            limit = params.get('limit', 100)
            return await client.get_references(doi, limit)
        
        elif function == 'search_articles':
            journal_code = params.get('journal_code')
            if not journal_code:
                return {'success': False, 'error': 'Missing required parameter: journal_code'}
            query = params.get('query')
            limit = params.get('limit', 20)
            return await client.search_articles(journal_code, query, limit)
        
        elif function == 'list_journals':
            return await client.list_journals()
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. '
                        f'Available functions: get_article_metadata, get_toc_current, get_toc_issue, '
                        f'get_references, search_articles, list_journals'
            }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        # Test article metadata
        print("Testing get_article_metadata...")
        result = await execute({'function': 'get_article_metadata', 'doi': '10.1086/739568'})
        print(json.dumps(result, indent=2)[:500])
        
        # Test TOC current
        print("\n" + "="*80)
        print("Testing get_toc_current...")
        result = await execute({'function': 'get_toc_current', 'journal_code': 'ajs'})
        print(json.dumps(result, indent=2)[:800])
        
        # Test list journals
        print("\n" + "="*80)
        print("Testing list_journals...")
        result = await execute({'function': 'list_journals'})
        print(json.dumps(result, indent=2)[:500])
    
    asyncio.run(test())