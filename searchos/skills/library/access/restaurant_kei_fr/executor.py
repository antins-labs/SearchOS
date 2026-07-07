"""
Restaurant KEI (Paris) Access Skill
Fetches restaurant information and product/gift card catalog via HTTP.
"""

import aiohttp
import re
import json
from typing import Any


SHOP_DOMAIN = "restaurant-kei.fr"
SHOP_ACCESS_TOKEN = "d6455c25b4583fa0102271504c1b5ab4"
SHOPIFY_API_VERSION = "2024-01"


async def _fetch_html(url: str, timeout: int = 15) -> dict:
    """Fetch HTML content and extract text. Returns structured result."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, 
                                  timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    return {
                        'success': False,
                        'error': f'HTTP {resp.status}',
                        'url': url
                    }
                
                html = await resp.text()
                return {
                    'success': True,
                    'html': html,
                    'url': url
                }
        except asyncio.TimeoutError:
            return {'success': False, 'error': 'Timeout', 'url': url}
        except Exception as e:
            return {'success': False, 'error': str(e), 'url': url}


async def _query_shopify(query: str, timeout: int = 15) -> dict:
    """Execute a GraphQL query against Shopify Storefront API."""
    api_url = f"https://{SHOP_DOMAIN}/api/{SHOPIFY_API_VERSION}/graphql.json"
    headers = {
        'X-Shopify-Storefront-Access-Token': SHOP_ACCESS_TOKEN,
        'Content-Type': 'application/json',
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_url, 
                                   headers=headers, 
                                   json={'query': query},
                                   timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    return {
                        'success': False,
                        'error': f'HTTP {resp.status}'
                    }
                
                data = await resp.json()
                if 'errors' in data:
                    return {
                        'success': False,
                        'error': data['errors'][0].get('message', 'GraphQL error'),
                        'errors': data['errors']
                    }
                
                return {
                    'success': True,
                    'data': data.get('data', {})
                }
        except asyncio.TimeoutError:
            return {'success': False, 'error': 'Timeout'}
        except Exception as e:
            return {'success': False, 'error': str(e)}


def _extract_text_content(html: str) -> dict:
    """Extract structured content from HTML."""
    # Remove scripts, styles, noscript
    html_clean = re.sub(r'<(script|style|noscript|svg|path)[^>]*>.*?</\1>', '', 
                       html, flags=re.DOTALL | re.IGNORECASE)
    
    # Get body
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_clean, re.DOTALL | re.IGNORECASE)
    if not body_match:
        return {'text': '', 'lines': []}
    
    body = body_match.group(1)
    text = re.sub(r'<[^>]+>', '\n', body)
    text = re.sub(r'&[^;]+;', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r' +', ' ', text)
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    return {
        'text': text.strip(),
        'lines': lines
    }


def _extract_restaurant_info(html: str) -> dict:
    """Extract restaurant information from HTML."""
    content = _extract_text_content(html)
    lines = content['lines']
    
    info = {
        'name': 'Restaurant KEI',
        'chef': 'Kei Kobayashi',
        'address': {},
        'contact': {},
        'hours': [],
        'notes': []
    }
    
    # Extract unique meaningful lines
    seen = set()
    unique_lines = []
    for line in lines:
        if len(line) > 5 and line not in seen:
            seen.add(line)
            unique_lines.append(line)
    
    for i, line in enumerate(unique_lines):
        # Address
        if re.search(r'\d+\s+rue', line, re.IGNORECASE):
            info['address']['street'] = line
        elif re.search(r'75001\s*paris', line, re.IGNORECASE):
            info['address']['city'] = line
            
        # Phone (French format: 01 42 33 14 74)
        phone_match = re.search(r'0[1-9]\s*\d{2}\s*\d{2}\s*\d{2}\s*\d{2}', line)
        if phone_match:
            info['contact']['phone'] = phone_match.group(0)
            
        # Email
        if '@' in line and '.' in line and len(line) < 100 and 'logo' not in line.lower():
            email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line)
            if email_match:
                email = email_match.group(0)
                if 'reservation' in email.lower():
                    info['contact']['reservation_email'] = email
                elif 'recrutement' not in email.lower():
                    info['contact'].setdefault('emails', []).append(email)
        
        # Hours
        if any(day in line.lower() for day in ['tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 
                                                'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']):
            info['hours'].append(line)
        elif re.search(r'\d{1,2}:\d{2}', line) or re.search(r'\d{1,2}h\d{0,2}', line, re.IGNORECASE):
            if any(kw in line.lower() for kw in ['p.m', 'pm', 'h', ':', 'lunch', 'dinner', 'midi', 'soir']):
                if len(line) < 100:
                    info['hours'].append(line)
        
        # Important notes
        if any(kw in line.lower() for kw in ['pets', 'children', 'cancellation', 'dress code', 'valet', 
                                              'animaux', 'enfants', 'annulation', 'voiturier']):
            info['notes'].append(line)
    
    # Clean up hours
    if info['hours']:
        info['hours_formatted'] = _format_hours(info['hours'])
    
    return info


def _format_hours(hours_lines: list) -> list:
    """Format opening hours into structured data."""
    formatted = []
    for line in hours_lines[:10]:  # Limit to 10 lines
        formatted.append(line)
    return formatted


async def fetch_home_page(params: dict, ctx: Any = None) -> dict:
    """Fetch restaurant information from the home page."""
    lang = params.get('lang', 'en')
    url = f"https://{SHOP_DOMAIN}/{lang}/"
    
    result = await _fetch_html(url)
    
    if not result['success']:
        return result
    
    info = _extract_restaurant_info(result['html'])
    
    return {
        'success': True,
        'restaurant': info,
        'url': url
    }


async def list_products(params: dict, ctx: Any = None) -> dict:
    """List all products from Shopify store (gift cards, books, etc.)."""
    limit = min(params.get('limit', 50), 250)
    product_type = params.get('product_type')
    
    filter_str = ""
    if product_type:
        filter_str = f', query: "product_type:{product_type}"'
    
    query = f"""
    {{
      products(first: {limit}{filter_str}) {{
        edges {{
          node {{
            id
            title
            handle
            description
            productType
            tags
            availableForSale
            priceRange {{
              minVariantPrice {{
                amount
                currencyCode
              }}
              maxVariantPrice {{
                amount
                currencyCode
              }}
            }}
            variants(first: 5) {{
              edges {{
                node {{
                  id
                  title
                  price {{
                    amount
                    currencyCode
                  }}
                  availableForSale
                }}
              }}
            }}
            images(first: 1) {{
              edges {{
                node {{
                  url
                  altText
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    
    result = await _query_shopify(query)
    
    if not result['success']:
        return result
    
    products_data = result['data'].get('products', {})
    edges = products_data.get('edges', [])
    
    products = []
    for edge in edges:
        node = edge['node']
        product = {
            'id': node['id'],
            'title': node['title'],
            'handle': node['handle'],
            'description': node.get('description', ''),
            'product_type': node.get('productType', ''),
            'tags': node.get('tags', []),
            'available': node.get('availableForSale', False),
            'price': float(node['priceRange']['minVariantPrice']['amount']),
            'currency': node['priceRange']['minVariantPrice']['currencyCode'],
            'url': f"https://{SHOP_DOMAIN}/products/{node['handle']}"
        }
        
        if node['images']['edges']:
            product['image'] = node['images']['edges'][0]['node']['url']
        
        variants = []
        for v in node['variants']['edges']:
            variants.append({
                'id': v['node']['id'],
                'title': v['node']['title'],
                'price': float(v['node']['price']['amount']),
                'available': v['node']['availableForSale']
            })
        if len(variants) > 1:
            product['variants'] = variants
        
        products.append(product)
    
    return {
        'success': True,
        'products': products,
        'count': len(products)
    }


async def list_collections(params: dict, ctx: Any = None) -> dict:
    """List all product collections."""
    limit = min(params.get('limit', 20), 250)
    
    query = f"""
    {{
      collections(first: {limit}) {{
        edges {{
          node {{
            id
            title
            handle
            description
            products(first: 10) {{
              edges {{
                node {{
                  id
                  title
                  handle
                  productType
                  priceRange {{
                    minVariantPrice {{
                      amount
                      currencyCode
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    
    result = await _query_shopify(query)
    
    if not result['success']:
        return result
    
    collections_data = result['data'].get('collections', {})
    edges = collections_data.get('edges', [])
    
    collections = []
    for edge in edges:
        node = edge['node']
        collection = {
            'id': node['id'],
            'title': node['title'],
            'handle': node['handle'],
            'description': node.get('description', ''),
            'url': f"https://{SHOP_DOMAIN}/collections/{node['handle']}"
        }
        
        products = []
        for p in node['products']['edges']:
            products.append({
                'id': p['node']['id'],
                'title': p['node']['title'],
                'product_type': p['node'].get('productType', ''),
                'price': float(p['node']['priceRange']['minVariantPrice']['amount'])
            })
        
        if products:
            collection['products'] = products
            collection['product_count'] = len(products)
        
        collections.append(collection)
    
    return {
        'success': True,
        'collections': collections,
        'count': len(collections)
    }


async def get_product(params: dict, ctx: Any = None) -> dict:
    """Get detailed information about a specific product."""
    handle = params.get('handle')
    product_id = params.get('product_id')
    
    if not handle and not product_id:
        return {
            'success': False,
            'error': 'Either handle or product_id is required'
        }
    
    if handle:
        query = f"""
        {{
          product(handle: "{handle}") {{
            id
            title
            handle
            description
            descriptionHtml
            productType
            tags
            availableForSale
            priceRange {{
              minVariantPrice {{
                amount
                currencyCode
              }}
              maxVariantPrice {{
                amount
                currencyCode
              }}
            }}
            variants(first: 20) {{
              edges {{
                node {{
                  id
                  title
                  price {{
                    amount
                    currencyCode
                  }}
                  availableForSale
                  selectedOptions {{
                    name
                    value
                  }}
                }}
              }}
            }}
            images(first: 5) {{
              edges {{
                node {{
                  url
                  altText
                }}
              }}
            }}
          }}
        }}
        """
    else:
        query = f"""
        {{
          node(id: "{product_id}") {{
            ... on Product {{
              id
              title
              handle
              description
              descriptionHtml
              productType
              tags
              availableForSale
              priceRange {{
                minVariantPrice {{
                  amount
                  currencyCode
                }}
                maxVariantPrice {{
                  amount
                  currencyCode
                }}
              }}
              variants(first: 20) {{
                edges {{
                  node {{
                    id
                    title
                    price {{
                      amount
                      currencyCode
                    }}
                    availableForSale
                    selectedOptions {{
                      name
                      value
                    }}
                  }}
                }}
              }}
              images(first: 5) {{
                edges {{
                  node {{
                    url
                    altText
                  }}
                }}
              }}
            }}
          }}
        }}
        """
    
    result = await _query_shopify(query)
    
    if not result['success']:
        return result
    
    product = result['data'].get('product') or result['data'].get('node')
    
    if not product:
        return {
            'success': False,
            'error': 'Product not found'
        }
    
    detailed = {
        'id': product['id'],
        'title': product['title'],
        'handle': product['handle'],
        'description': product.get('description', ''),
        'product_type': product.get('productType', ''),
        'tags': product.get('tags', []),
        'available': product.get('availableForSale', False),
        'price_min': float(product['priceRange']['minVariantPrice']['amount']),
        'price_max': float(product['priceRange']['maxVariantPrice']['amount']),
        'currency': product['priceRange']['minVariantPrice']['currencyCode'],
        'url': f"https://{SHOP_DOMAIN}/products/{product['handle']}"
    }
    
    images = []
    for img in product['images']['edges']:
        images.append({
            'url': img['node']['url'],
            'alt': img['node'].get('altText', '')
        })
    if images:
        detailed['images'] = images
    
    variants = []
    for v in product['variants']['edges']:
        variants.append({
            'id': v['node']['id'],
            'title': v['node']['title'],
            'price': float(v['node']['price']['amount']),
            'available': v['node']['availableForSale'],
            'options': v['node'].get('selectedOptions', [])
        })
    if variants:
        detailed['variants'] = variants
    
    return {
        'success': True,
        'product': detailed
    }


async def get_collection(params: dict, ctx: Any = None) -> dict:
    """Get detailed information about a specific collection."""
    handle = params.get('handle')
    
    if not handle:
        return {
            'success': False,
            'error': 'Collection handle is required'
        }
    
    limit = min(params.get('limit', 50), 250)
    
    query = f"""
    {{
      collection(handle: "{handle}") {{
        id
        title
        handle
        description
        descriptionHtml
        products(first: {limit}) {{
          edges {{
            node {{
              id
              title
              handle
              description
              productType
              availableForSale
              priceRange {{
                minVariantPrice {{
                  amount
                  currencyCode
                }}
              }}
              images(first: 1) {{
                edges {{
                  node {{
                    url
                    altText
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    
    result = await _query_shopify(query)
    
    if not result['success']:
        return result
    
    collection = result['data'].get('collection')
    
    if not collection:
        return {
            'success': False,
            'error': 'Collection not found'
        }
    
    detailed = {
        'id': collection['id'],
        'title': collection['title'],
        'handle': collection['handle'],
        'description': collection.get('description', ''),
        'url': f"https://{SHOP_DOMAIN}/collections/{collection['handle']}"
    }
    
    products = []
    for edge in collection['products']['edges']:
        node = edge['node']
        product = {
            'id': node['id'],
            'title': node['title'],
            'handle': node['handle'],
            'description': node.get('description', ''),
            'product_type': node.get('productType', ''),
            'available': node.get('availableForSale', False),
            'price': float(node['priceRange']['minVariantPrice']['amount']),
            'currency': node['priceRange']['minVariantPrice']['currencyCode'],
            'url': f"https://{SHOP_DOMAIN}/products/{node['handle']}"
        }
        
        if node['images']['edges']:
            product['image'] = node['images']['edges'][0]['node']['url']
        
        products.append(product)
    
    detailed['products'] = products
    detailed['product_count'] = len(products)
    
    return {
        'success': True,
        'collection': detailed
    }


async def get_contact_info(params: dict, ctx: Any = None) -> dict:
    """Get restaurant contact information."""
    result = await fetch_home_page({'lang': 'en'}, ctx)
    
    if not result['success']:
        return result
    
    restaurant = result.get('restaurant', {})
    contact = restaurant.get('contact', {})
    address = restaurant.get('address', {})
    hours = restaurant.get('hours_formatted', [])
    
    contact_info = {
        'name': 'Restaurant KEI',
        'chef': 'Kei Kobayashi',
        'address': {
            'street': address.get('street', '5 Rue Coq Héron'),
            'city': address.get('city', '75001 Paris'),
            'country': 'France'
        },
        'phone': contact.get('phone', '01 42 33 14 74'),
        'email': contact.get('reservation_email', 'reservationkei@gmail.com'),
        'www': 'https://restaurant-kei.fr',
        'booking_note': 'Reservations open two months in advance, on the first Tuesday of each month'
    }
    
    if hours:
        contact_info['opening_hours'] = hours
    
    return {
        'success': True,
        'contact': contact_info
    }


# Exported function dispatcher
async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute a function call for the Restaurant KEI skill.
    
    Parameters:
        params: dict with 'function' key specifying which function to call
        ctx: optional context
    
    Returns:
        dict with 'success' key and data or error information
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function'
        }
    
    handlers = {
        'fetch_home_page': fetch_home_page,
        'list_products': list_products,
        'list_collections': list_collections,
        'get_product': get_product,
        'get_collection': get_collection,
        'get_contact_info': get_contact_info,
    }
    
    handler = handlers.get(function)
    
    if not handler:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'available_functions': list(handlers.keys())
        }
    
    try:
        return await handler(params, ctx)
    except Exception as e:
        return {
            'success': False,
            'error': f'Execution error: {str(e)}'
        }