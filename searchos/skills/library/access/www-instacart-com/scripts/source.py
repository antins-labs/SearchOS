"""
Instacart Product Page Access Skill

Fetches product information from Instacart cross-retailer product detail pages.
Extracts product details, nutrition info, ingredients, and pricing from embedded JSON data.
"""

import asyncio
import aiohttp
import json
import re
from urllib.parse import unquote
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Instacart product page fetch.
    
    Args:
        params: Dictionary containing:
            - function: "get_product" to fetch product details
            - url: Product URL (optional, can use product_id instead)
            - product_id: Instacart product ID (optional, extracted from URL if not provided)

    
    Returns:
        Dictionary with product information or error details
    """
    function = params.get("function")
    
    if function == "get_product":
        return await get_product(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Supported: get_product"
        }


async def get_product(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch product details from Instacart.
    
    Accepts either:
    - url: Full Instacart product URL
    - product_id: Numeric product ID
    """
    url = params.get("url")
    product_id = params.get("product_id")
    product_slug = None
    
    # Extract product ID and slug from URL if needed
    if url and not product_id:
        product_id, product_slug = extract_product_info(url)
    elif url:
        _, product_slug = extract_product_info(url)
    
    if not product_id:
        return {
            "success": False,
            "error": "Either 'url' or 'product_id' is required"
        }
    
    # Construct the cross-retailer PDP URL
    # Need the slug for the page to load properly
    if product_slug:
        product_url = f"https://www.instacart.com/store/products/{product_id}-{product_slug}?x_retailer=true"
    else:
        # Without slug, we need to discover it first
        product_url = f"https://www.instacart.com/store/products/{product_id}?x_retailer=true"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # Try to fetch the product page
            async with session.get(product_url, headers=headers, timeout=30, allow_redirects=False) as response:
                if response.status == 302:
                    # Handle redirect from /products/ to /store/products/
                    redirect_url = response.headers.get('Location', '')
                    if redirect_url.startswith('/'):
                        redirect_url = f"https://www.instacart.com{redirect_url}"
                    
                    # Extract slug from redirect if we don't have it
                    if not product_slug:
                        _, product_slug = extract_product_info(redirect_url)
                        if product_slug:
                            product_url = f"https://www.instacart.com/store/products/{product_id}-{product_slug}?x_retailer=true"
                        else:
                            product_url = redirect_url
                            if 'x_retailer' not in product_url:
                                product_url = f"{product_url}&x_retailer=true" if '?' in product_url else f"{product_url}?x_retailer=true"
                    
                    # Fetch the redirected URL
                    async with session.get(product_url, headers=headers, timeout=30) as redirect_response:
                        if redirect_response.status != 200:
                            return {
                                "success": False,
                                "error": f"HTTP {redirect_response.status}: Failed to fetch product page after redirect",
                                "product_id": product_id
                            }
                        html = await redirect_response.text()
                        product_url = str(redirect_response.url)
                
                elif response.status == 200:
                    html = await response.text()
                    
                    # Check if we need to follow a JavaScript redirect
                    if len(html) < 50000:
                        redirect_match = re.search(r'window\.location\.replace\("([^"]+)"', html)
                        if redirect_match:
                            redirect_url = redirect_match.group(1)
                            if redirect_url.startswith('/'):
                                redirect_url = f"https://www.instacart.com{redirect_url}"
                            
                            # Extract slug from redirect
                            if not product_slug:
                                _, product_slug = extract_product_info(redirect_url)
                            
                            if product_slug:
                                redirect_url = f"https://www.instacart.com/store/products/{product_id}-{product_slug}?x_retailer=true"
                            elif 'x_retailer' not in redirect_url:
                                redirect_url = f"{redirect_url}&x_retailer=true" if '?' in redirect_url else f"{redirect_url}?x_retailer=true"
                            
                            async with session.get(redirect_url, headers=headers, timeout=30) as js_redirect_response:
                                if js_redirect_response.status != 200:
                                    return {
                                        "success": False,
                                        "error": f"HTTP {js_redirect_response.status}: Failed to fetch product page after JS redirect",
                                        "product_id": product_id
                                    }
                                html = await js_redirect_response.text()
                                product_url = redirect_url
                
                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: Failed to fetch product page",
                        "product_id": product_id
                    }
            
            # Check if we have enough data
            if len(html) < 50000:
                return {
                    "success": False,
                    "error": "Product page returned insufficient data - product may not exist or be unavailable",
                    "product_id": product_id,
                    "html_length": len(html)
                }
            
            # Extract product data from embedded JSON
            product_data = extract_product_data(html)
            
            if not product_data:
                return {
                    "success": False,
                    "error": "Could not extract product data from page - product may not exist",
                    "product_id": product_id
                }
            
            product_data["product_id"] = product_id
            product_data["source_url"] = product_url
            product_data["success"] = True
            
            return product_data
                
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timed out",
            "product_id": product_id
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error fetching product: {str(e)}",
            "product_id": product_id
        }


def extract_product_info(url: str) -> tuple[str | None, str | None]:
    """Extract product ID and slug from Instacart URL."""
    # Match patterns like:
    # - /products/20248583-rowdy-mermaid-rowdy-belly-12-fl-oz
    # - /store/products/20248583-rowdy-mermaid-rowdy-belly-12-fl-oz
    # - /store/products/20248583
    
    patterns = [
        r'/products/(\d+)(?:-([^/?]+))?',
        r'/store/products/(\d+)(?:-([^/?]+))?',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            product_id = match.group(1)
            slug = match.group(2) if match.lastindex >= 2 else None
            return product_id, slug
    
    # Try to extract just the ID
    id_match = re.search(r'product_id[=:]\s*["\']?(\d+)', url)
    if id_match:
        return id_match.group(1), None
    
    return None, None


def extract_product_data(html: str) -> dict[str, Any] | None:
    """Extract product data from HTML page."""
    # Find URL-encoded JSON scripts
    script_pattern = r'<script[^>]*>([^<]+)</script>'
    scripts = re.findall(script_pattern, html)
    
    product_info = {}
    detail_sections = []
    
    for script in scripts:
        # Check for URL-encoded JSON (starts with %7B which is {)
        if script.strip().startswith('%7B'):
            try:
                decoded = unquote(script)
                data = json.loads(decoded)
                
                # Extract from CrossRetailerProductDetailProductCoreInfo
                if 'CrossRetailerProductDetailProductCoreInfo' in data:
                    core_info = data['CrossRetailerProductDetailProductCoreInfo']
                    for key, value in core_info.items():
                        if isinstance(value, dict) and 'landingProducts' in value and value['landingProducts']:
                            p = value['landingProducts'][0]
                            product_info['name'] = p.get('name')
                            product_info['brand'] = p.get('brandName')
                            product_info['size'] = p.get('size')
                            product_info['category'] = p.get('productCategoryName')
                            product_info['category_id'] = p.get('productCategoryId')
                            
                            if p.get('productFallbackPricing'):
                                product_info['starting_price'] = p['productFallbackPricing'].get('startingPrice')
                            
                            if p.get('productInfo'):
                                pi = p['productInfo']
                                product_info['description'] = pi.get('description')
                                
                                if pi.get('viewSection'):
                                    vs = pi['viewSection']
                                    product_info['meta_title'] = vs.get('metaTitleString')
                                    product_info['meta_description'] = clean_html_tags(vs.get('metaDescriptionString', ''))
                                    
                                    # Extract product detail sections (details, ingredients, directions, etc.)
                                    if 'productDetailSections' in vs:
                                        for section in vs['productDetailSections']:
                                            section_data = {
                                                'type': section.get('sectionTypeVariant'),
                                                'header': section.get('headerString'),
                                                'body': section.get('bodyString')
                                            }
                                            if section_data['body']:
                                                detail_sections.append(section_data)
                
                # Extract from CrossRetailerProductDetailFaqs
                if 'CrossRetailerProductDetailFaqs' in data:
                    faqs = data['CrossRetailerProductDetailFaqs']
                    for key, value in faqs.items():
                        if isinstance(value, dict) and 'landingFaqs' in value:
                            lf = value['landingFaqs']
                            product_info['has_nutritional_info'] = lf.get('hasNutritionalInfo')
                            product_info['gluten_free'] = lf.get('glutenFree')
                            
                            if 'viewSection' in lf:
                                vs = lf['viewSection']
                                # Extract calorie info
                                if 'answerOnCaloriesString' in vs:
                                    calories_match = re.search(r'(\d+)\s*calories', vs['answerOnCaloriesString'], re.IGNORECASE)
                                    if calories_match:
                                        product_info['calories'] = int(calories_match.group(1))
                
                # Extract images
                if 'CrossRetailerProductDetailProductImages' in data:
                    images_data = data['CrossRetailerProductDetailProductImages']
                    for key, value in images_data.items():
                        if isinstance(value, dict) and 'landingRetailerProductImages' in value:
                            images = value['landingRetailerProductImages'].get('images', [])
                            if images:
                                product_info['images'] = [
                                    img.get('viewSection', {}).get('retailerProductImage', {}).get('templateUrl')
                                    for img in images
                                    if img.get('viewSection', {}).get('retailerProductImage', {}).get('templateUrl')
                                ]
                
                # Extract breadcrumbs
                if 'CrossRetailerProductDetailBreadcrumbs' in data:
                    breadcrumbs = data['CrossRetailerProductDetailBreadcrumbs']
                    for key, value in breadcrumbs.items():
                        if isinstance(value, dict) and 'landingProductBreadcrumbs' in value:
                            bc = value['landingProductBreadcrumbs'].get('breadcrumbs', [])
                            product_info['breadcrumbs'] = [
                                {
                                    'name': b.get('viewSection', {}).get('textString'),
                                    'url': b.get('url')
                                }
                                for b in bc
                            ]
                
            except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
                continue
    
    # Process detail sections into structured data
    if detail_sections:
        for section in detail_sections:
            section_type = section.get('type', '').lower()
            body = section.get('body', '')
            
            if section_type == 'ingredients':
                product_info['ingredients'] = body
                # Parse ingredients list
                if body:
                    product_info['ingredients_list'] = [i.strip() for i in re.split(r'[,,\n]+', body) if i.strip()]
            
            elif section_type == 'details':
                product_info['details'] = body
            
            elif section_type == 'directions':
                product_info['directions'] = body
            
            elif section_type == 'nutrition' or 'nutrition' in section_type:
                product_info['nutrition_facts'] = body
    
    # Return None if we didn't extract any meaningful data
    if not product_info.get('name'):
        return None
    
    # Add detail sections for reference
    if detail_sections:
        product_info['all_sections'] = detail_sections
    
    return product_info


def clean_html_tags(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return text
    return re.sub(r'<[^>]+>', '', text)