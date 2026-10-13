"""
SearchOS access skill for www.lzljglobal.com - 泸州老窖国际发展（香港）有限公司 product catalog.
"""

from typing import Any
import aiohttp
from bs4 import BeautifulSoup


BASE_URL = "https://www.lzljglobal.com"

# Known product categories
CATEGORIES = {
    "15": "国窖1573",
    "16": "泸州老窖头曲", 
    "17": "泸州老窖二曲",
    "18": "泸州老窖特曲",
}


async def fetch_html(url: str, timeout: int = 30) -> str:
    """Fetch HTML content from URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            response.raise_for_status()
            return await response.text()


def parse_product_list(html: str, category_id: str) -> list[dict[str, Any]]:
    """Parse product list from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    products = []
    
    for item in soup.find_all('li'):
        link = item.find('a', href=lambda x: x and f'/col{category_id}/' in x and '/list' not in x)
        if link:
            href = link.get('href')
            
            # Extract title
            img = item.find('img')
            h4 = item.find('h4')
            title = (img.get('alt') if img else None) or (h4.get_text(strip=True) if h4 else '')
            
            # Extract image
            image_url = img.get('src') if img else None
            if image_url and not image_url.startswith('http'):
                image_url = BASE_URL + image_url
            
            # Extract product ID from URL
            product_id = href.split('/')[-1] if href else None
            
            products.append({
                'product_id': product_id,
                'title': title,
                'url': BASE_URL + href if href else None,
                'image': image_url,
                'category_id': category_id,
            })
    
    return products


def parse_product_detail(html: str, category_id: str, product_id: str) -> dict[str, Any]:
    """Parse product detail page."""
    soup = BeautifulSoup(html, 'html.parser')
    
    product = {
        'product_id': product_id,
        'category_id': category_id,
        'url': f"{BASE_URL}/col{category_id}/{product_id}",
    }
    
    # Title
    title_elem = soup.find('h1') or soup.find(class_=lambda x: x and 'title' in str(x).lower() if x else False)
    if title_elem:
        product['title'] = title_elem.get_text(strip=True)
    
    # Product images (filter by category)
    images = []
    for img in soup.find_all('img', src=lambda x: x and 'upload/image' in x):
        src = img.get('src')
        # Only get images from the same category
        if f'/col{category_id}/' in src:
            alt = img.get('alt', '')
            full_url = BASE_URL + src if src.startswith('/') else src
            images.append({'url': full_url, 'alt': alt})
    
    # Remove duplicates while preserving order
    seen = set()
    unique_images = []
    for img in images:
        if img['url'] not in seen:
            seen.add(img['url'])
            unique_images.append(img)
    
    product['images'] = unique_images
    
    # Extract main image (first unique product image)
    if unique_images:
        product['main_image'] = unique_images[0]['url']
    
    # Find product details section
    detail_section = soup.find(class_=lambda x: x and 'product-detail' in x.lower() if x else False)
    if not detail_section:
        detail_section = soup.find('section') or soup.find('article')
    
    if detail_section:
        # Extract full text content
        full_text = detail_section.get_text(separator='|', strip=True)
        
        # Parse specifications from structured content
        specs = {}
        parts = full_text.split('|')
        for i, part in enumerate(parts):
            part = part.strip()
            if part == '产品度数' and i + 1 < len(parts):
                specs['alcohol_content'] = parts[i + 1].strip()
            elif part == '产品规格' and i + 1 < len(parts):
                specs['specification'] = parts[i + 1].strip()
        
        if specs:
            product['specifications'] = specs
        
        # Extract description (text after specifications)
        paragraphs = []
        in_desc = False
        for i, part in enumerate(parts):
            part = part.strip()
            
            # Skip empty or very short parts
            if not part or len(part) < 10:
                continue
            
            # Skip title
            if part == product.get('title'):
                continue
            
            # Skip specification labels and values
            if part in ['产品度数', '产品规格']:
                continue
            if part in specs.values():
                continue
            
            # Start capturing after specifications
            if '产品规格' in parts[max(0, i-3):i]:
                in_desc = True
            
            if in_desc and len(part) > 20:
                # Stop at navigation or related products
                if any(stop in part for stop in ['系列产品', '首页', '品牌资讯', '历史与传承', '关于我们']):
                    break
                paragraphs.append(part)
        
        # Join multiple description paragraphs
        if paragraphs:
            product['description'] = ' '.join(paragraphs)
    
    # If description wasn't found, try alternative extraction
    if 'description' not in product:
        for elem in soup.find_all(['p', 'div']):
            text = elem.get_text(strip=True)
            if len(text) > 100 and '产品度数' not in text and product.get('title', '') not in text[:50]:
                # Make sure it's not navigation text
                if '首页' not in text and '品牌资讯' not in text and '系列产品' not in text:
                    product['description'] = text
                    break
    
    return product


async def list_products(category_id: str = None, page: int = 1) -> dict[str, Any]:
    """
    List products from a category with pagination.
    """
    if not category_id:
        return {
            'success': False,
            'error': 'category_id is required',
            'categories': CATEGORIES,
        }
    
    if category_id not in CATEGORIES:
        return {
            'success': False,
            'error': f'Invalid category_id. Valid categories: {list(CATEGORIES.keys())}',
            'categories': CATEGORIES,
        }
    
    # Build URL for pagination
    if page <= 1:
        url = f"{BASE_URL}/col{category_id}/list"
    else:
        url = f"{BASE_URL}/col{category_id}/list_{page}"
    
    try:
        html = await fetch_html(url)
        products = parse_product_list(html, category_id)
        
        return {
            'success': True,
            'category_id': category_id,
            'category_name': CATEGORIES[category_id],
            'page': page,
            'products': products,
            'count': len(products),
            'url': url,
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url,
        }


async def get_product_detail(category_id: str, product_id: str) -> dict[str, Any]:
    """
    Get detailed product information.
    """
    if not category_id or not product_id:
        return {
            'success': False,
            'error': 'Both category_id and product_id are required',
        }
    
    url = f"{BASE_URL}/col{category_id}/{product_id}"
    
    try:
        html = await fetch_html(url)
        product = parse_product_detail(html, category_id, product_id)
        
        return {
            'success': True,
            **product,
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'url': url,
        }


async def search_products(query: str, category_id: str = None) -> dict[str, Any]:
    """
    Search products by title across categories.
    """
    results = []
    categories_to_search = [category_id] if category_id else list(CATEGORIES.keys())
    
    for cat_id in categories_to_search:
        if cat_id not in CATEGORIES:
            continue
        
        try:
            # Search first page of each category
            html = await fetch_html(f"{BASE_URL}/col{cat_id}/list")
            products = parse_product_list(html, cat_id)
            
            # Filter by query
            query_lower = query.lower()
            for product in products:
                if query_lower in product.get('title', '').lower():
                    results.append(product)
        except Exception:
            continue
    
    return {
        'success': True,
        'query': query,
        'results': results,
        'count': len(results),
    }


async def get_categories() -> dict[str, Any]:
    """
    Get all available product categories.
    """
    return {
        'success': True,
        'categories': [
            {
                'category_id': cat_id,
                'name': name,
                'url': f"{BASE_URL}/col{cat_id}/list",
            }
            for cat_id, name in CATEGORIES.items()
        ],
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute API calls for www.lzljglobal.com product catalog.
    
    Args:
        params: Dictionary containing:
            - function: One of 'list_products', 'get_product', 'search_products', 'get_categories'
            - category_id: Category ID (required for list_products, optional for search)
            - product_id: Product ID (required for get_product)
            - page: Page number (optional, for list_products, default=1)
            - query: Search query (required for search_products)
    
    Returns:
        Dictionary with results or error information.
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'function parameter is required',
        }
    
    if function == 'list_products':
        category_id = params.get('category_id')
        page = params.get('page', 1)
        return await list_products(category_id=category_id, page=int(page))
    
    elif function == 'get_product':
        category_id = params.get('category_id')
        product_id = params.get('product_id')
        return await get_product_detail(category_id=category_id, product_id=product_id)
    
    elif function == 'search_products':
        query = params.get('query')
        category_id = params.get('category_id')
        return await search_products(query=query, category_id=category_id)
    
    elif function == 'get_categories':
        return await get_categories()
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Valid functions: list_products, get_product, search_products, get_categories',
        }