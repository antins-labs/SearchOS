"""
Johnnie Walker Product Catalog Access Skill

This skill provides access to Johnnie Walker's whisky product catalog
via their public search API.
"""

import asyncio
import aiohttp
from typing import Any, Dict, List, Optional
import json


class JohnnieWalkerAPI:
    """Client for Johnnie Walker product API"""
    
    BASE_URL = "https://www.johnniewalker.com/api/search"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://www.johnniewalker.com/'
        }
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def search_products(
        self,
        query: str = "",
        limit: int = 50,
        locale: str = "en-us",
        sort_by: str = "trending"
    ) -> Dict[str, Any]:
        """
        Search for products using the Johnnie Walker API
        
        Args:
            query: Search query string
            limit: Maximum number of results
            locale: Locale for products (e.g., 'en-us')
            sort_by: Sort order (trending, az, za, age)
        
        Returns:
            Dictionary with search results or error information
        """
        try:
            session = await self._get_session()
            
            params = {
                'indexName': f'index_products_prod_{sort_by}',
                'query': query,
                'sortBy': sort_by,
                'limit': limit,
                'filters': f"locale:'{locale}'",
                'numericFilters': ''
            }
            
            async with session.get(self.BASE_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Extract hits from results
                    hits = []
                    if data.get('results') and len(data['results']) > 0:
                        hits = data['results'][0].get('hits', [])
                    
                    return {
                        'success': True,
                        'total_results': len(hits),
                        'products': hits,
                        'query': query,
                        'locale': locale,
                        'sort_by': sort_by
                    }
                else:
                    text = await response.text()
                    return {
                        'success': False,
                        'error': f'API returned status {response.status}',
                        'details': text[:500]
                    }
                    
        except aiohttp.ClientError as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}'
            }
    
    async def get_all_products(
        self,
        limit: int = 100,
        locale: str = "en-us"
    ) -> Dict[str, Any]:
        """
        Get all available products
        
        Args:
            limit: Maximum number of results
            locale: Locale for products
        
        Returns:
            Dictionary with all products or error information
        """
        result = await self.search_products(
            query="",
            limit=limit,
            locale=locale,
            sort_by="trending"
        )
        
        if result.get('success'):
            result['function'] = 'get_all_products'
        
        return result
    
    async def get_products_by_group(
        self,
        group: str,
        limit: int = 50,
        locale: str = "en-us"
    ) -> Dict[str, Any]:
        """
        Get products filtered by group/category
        
        Valid groups: 'core-range', 'limited-editions', 'gift-boxes'
        
        Args:
            group: Product group name
            limit: Maximum number of results
            locale: Locale for products
        
        Returns:
            Dictionary with filtered products or error information
        """
        # First get all products, then filter by group
        result = await self.search_products(
            query="",
            limit=200,  # Get more to ensure we have all products
            locale=locale,
            sort_by="trending"
        )
        
        if not result.get('success'):
            return result
        
        # Filter by group
        all_products = result.get('products', [])
        filtered_products = [
            p for p in all_products
            if p.get('group') == group
        ][:limit]
        
        return {
            'success': True,
            'total_results': len(filtered_products),
            'products': filtered_products,
            'group': group,
            'locale': locale,
            'function': 'get_products_by_group'
        }


def format_product_summary(product: Dict[str, Any]) -> str:
    """Format a product for display"""
    lines = []
    
    # Title
    title = product.get('title', 'Unknown')
    lines.append(f"**{title}**")
    
    # Product range/group
    if product.get('group'):
        lines.append(f"Group: {product['group'].replace('-', ' ').title()}")
    
    # ABV and sizes
    if product.get('detailBottleSize'):
        lines.append(f"Details: {product['detailBottleSize']}")
    
    # Product features
    features = product.get('productFeatures', [])
    if features:
        lines.append(f"Features: {', '.join(features)}")
    
    # URL
    if product.get('url'):
        lines.append(f"URL: https://www.johnniewalker.com{product['url']}")
    
    # Buy link
    if product.get('buyNowLink', {}).get('url'):
        lines.append(f"Buy: {product['buyNowLink']['url']}")
    
    return '\n'.join(lines)


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the Johnnie Walker product skill
    
    Args:
        params: Dictionary containing:
            - function: Name of function to call (required if multiple functions available)
            - query: Search query (for search_products)
            - group: Product group (for get_products_by_group)
            - limit: Maximum results (optional)
            - locale: Product locale (optional)
        ctx: Context object (not used)
    
    Returns:
        Dictionary with results or error information
    """
    # Get function name
    function_name = params.get('function', 'get_all_products')
    
    # Initialize API client
    api = JohnnieWalkerAPI()
    
    try:
        # Execute requested function
        if function_name == 'search_products':
            query = params.get('query', '')
            limit = params.get('limit', 50)
            locale = params.get('locale', 'en-us')
            
            result = await api.search_products(
                query=query,
                limit=limit,
                locale=locale
            )
            result['function'] = 'search_products'
            
        elif function_name == 'get_all_products':
            limit = params.get('limit', 100)
            locale = params.get('locale', 'en-us')
            
            result = await api.get_all_products(
                limit=limit,
                locale=locale
            )
            
        elif function_name == 'get_products_by_group':
            group = params.get('group')
            if not group:
                return {
                    'success': False,
                    'error': 'Missing required parameter: group',
                    'valid_groups': ['core-range', 'limited-editions', 'gift-boxes']
                }
            
            limit = params.get('limit', 50)
            locale = params.get('locale', 'en-us')
            
            result = await api.get_products_by_group(
                group=group,
                limit=limit,
                locale=locale
            )
            
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function_name}',
                'available_functions': [
                    'search_products',
                    'get_all_products',
                    'get_products_by_group'
                ]
            }
        
        # Add formatted summary if products were found
        if result.get('success') and result.get('products'):
            result['summary'] = '\n\n'.join([
                format_product_summary(p) 
                for p in result['products'][:10]  # Limit summary to first 10
            ])
            
            # Add structured product list
            result['product_list'] = [
                {
                    'title': p.get('title'),
                    'group': p.get('group'),
                    'url': f"https://www.johnniewalker.com{p.get('url')}" if p.get('url') else None,
                    'buy_url': p.get('buyNowLink', {}).get('url'),
                    'details': p.get('detailBottleSize'),
                    'features': p.get('productFeatures', []),
                    'sys_id': p.get('sysId')
                }
                for p in result['products']
            ]
        
        return result
        
    finally:
        await api.close()


# For testing
if __name__ == '__main__':
    async def test():
        print("=== Testing get_all_products ===")
        result = await execute({'function': 'get_all_products', 'limit': 5})
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n\n=== Testing search_products ===")
        result = await execute({'function': 'search_products', 'query': 'black', 'limit': 3})
        print(json.dumps(result, indent=2)[:2000])
        
        print("\n\n=== Testing get_products_by_group ===")
        result = await execute({'function': 'get_products_by_group', 'group': 'limited-editions', 'limit': 5})
        print(json.dumps(result, indent=2)[:2000])
    
    asyncio.run(test())