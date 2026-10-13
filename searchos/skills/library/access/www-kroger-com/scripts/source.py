"""
Kroger.com Product Page Access Skill

This skill fetches product data from Kroger.com product pages.
It handles anti-bot protections using browser automation with proper headers,
cookies, and JavaScript rendering.

The skill extracts:
- Product name
- Price (current and regular)
- UPC
- Brand
- Size/quantity
- Description
- Availability
- Product images
"""

import asyncio
import json
import re
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Kroger product page access.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ('get_product' or 'search_products')
            - url: Product page URL (for get_product)
            - upc: Product UPC code (for get_product, alternative to url)
            - query: Search query (for search_products)

    
    Returns:
        Dictionary with product data or error information
    """
    function = params.get("function", "")
    
    if function == "get_product":
        return await get_product(params)
    elif function == "search_products":
        return await search_products(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_product", "search_products"]
        }


async def get_product(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a single product from Kroger.com.
    
    Requires either 'url' or 'upc' parameter.
    """
    url = params.get("url")
    upc = params.get("upc")
    
    if not url and not upc:
        return {
            "success": False,
            "error": "Either 'url' or 'upc' parameter is required"
        }
    
    # Construct URL from UPC if needed
    if upc and not url:
        # Kroger URLs typically include the UPC at the end
        url = f"https://www.kroger.com/p/product/{upc}"
    
    # Validate URL
    if not url.startswith("https://www.kroger.com/"):
        return {
            "success": False,
            "error": "URL must be from www.kroger.com domain"
        }
    
    try:
        result = await fetch_product_page(url)
        return result
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch product: {str(e)}",
            "error_type": type(e).__name__
        }


async def search_products(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for products on Kroger.com.
    
    Requires 'query' parameter.
    """
    query = params.get("query")
    
    if not query:
        return {
            "success": False,
            "error": "'query' parameter is required for search"
        }
    
    # Build search URL
    search_url = f"https://www.kroger.com/search?query={query}&searchType=default_search"
    
    try:
        result = await fetch_search_results(search_url, query)
        return result
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to search products: {str(e)}",
            "error_type": type(e).__name__
        }


async def fetch_product_page(url: str) -> dict[str, Any]:
    """
    Fetch and parse a Kroger product page using browser automation.
    """
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-http2',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        
        try:
            # Create context with realistic browser fingerprint
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                viewport={'width': 1920, 'height': 1080},
                java_script_enabled=True,
                # Set geolocation to a Kroger service area
                geolocation={'latitude': 39.9612, 'longitude': -83.0025},  # Columbus, OH
                permissions=['geolocation'],
            )
            
            # Add scripts to hide automation
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({
                        effectiveType: '4g',
                        rtt: 50,
                        downlink: 10
                    })
                });
            """)
            
            page = await context.new_page()
            
            # Set extra headers
            await page.set_extra_http_headers({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Cache-Control': 'max-age=0',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'sec-fetch-dest': 'document',
                'sec-fetch-mode': 'navigate',
                'sec-fetch-site': 'none',
                'sec-fetch-user': '?1',
                'upgrade-insecure-requests': '1',
            })
            
            # Navigate to the product page
            response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            if not response:
                return {
                    "success": False,
                    "error": "No response received from page"
                }
            
            if response.status == 403:
                return {
                    "success": False,
                    "error": "Access blocked (403 Forbidden) - anti-bot protection triggered"
                }
            
            if response.status == 404:
                return {
                    "success": False,
                    "error": "Product not found (404)"
                }
            
            # Wait for page to load
            await page.wait_for_timeout(3000)
            
            # Try to wait for product content
            try:
                await page.wait_for_selector('[data-qa="product-title"], h1[class*="product"], [class*="ProductDetails"]', timeout=10000)
            except:
                pass
            
            # Extract product data from page
            product_data = await extract_product_data(page, url)
            
            return product_data
            
        finally:
            await browser.close()


async def extract_product_data(page, url: str) -> dict[str, Any]:
    """
    Extract product data from a loaded Kroger product page.
    """
    result = {
        "success": True,
        "url": url,
        "source": "kroger.com"
    }
    
    # Try to get data from __NEXT_DATA__ (Next.js app data)
    next_data = await page.query_selector('script[id="__NEXT_DATA__"]')
    if next_data:
        try:
            data_text = await next_data.inner_text()
            data = json.loads(data_text)
            
            # Navigate the Next.js data structure to find product info
            props = data.get('props', {}).get('pageProps', {})
            
            # Product data might be in various locations
            product = props.get('product') or props.get('productDetails') or {}
            
            if product:
                result.update({
                    "name": product.get('productName') or product.get('name'),
                    "brand": product.get('brand') or product.get('brandName'),
                    "upc": product.get('upc') or product.get('upcNumber'),
                    "description": product.get('description') or product.get('longDescription'),
                    "size": product.get('size') or product.get('packageSize'),
                    "images": product.get('images') or product.get('productImages', []),
                    "price": extract_price_data(product),
                    "category": product.get('category') or product.get('categoryId'),
                    "availability": product.get('availability') or product.get('stockStatus'),
                })
        except json.JSONDecodeError:
            pass
    
    # Also try to extract from visible page elements
    try:
        # Product title
        title_elem = await page.query_selector('[data-qa="product-title"], h1[class*="ProductTitle"], h1[data-testid="product-title"]')
        if title_elem:
            title_text = await title_elem.inner_text()
            if title_text and not result.get('name'):
                result['name'] = title_text.strip()
        
        # Price
        price_elem = await page.query_selector('[data-qa="product-price"], [class*="price"], [data-testid="current-price"]')
        if price_elem:
            price_text = await price_elem.inner_text()
            if price_text and not result.get('price'):
                result['price'] = parse_price_text(price_text)
        
        # UPC from URL
        upc_match = re.search(r'/(\d{10,14})/?$', url)
        if upc_match and not result.get('upc'):
            result['upc'] = upc_match.group(1)
        
        # Brand
        brand_elem = await page.query_selector('[data-qa="product-brand"], [class*="brand-name"]')
        if brand_elem:
            brand_text = await brand_elem.inner_text()
            if brand_text and not result.get('brand'):
                result['brand'] = brand_text.strip()
        
        # Size
        size_elem = await page.query_selector('[data-qa="product-size"], [class*="product-size"]')
        if size_elem:
            size_text = await size_elem.inner_text()
            if size_text and not result.get('size'):
                result['size'] = size_text.strip()
        
        # Description
        desc_elem = await page.query_selector('[data-qa="product-description"], [class*="description"], [itemprop="description"]')
        if desc_elem:
            desc_text = await desc_elem.inner_text()
            if desc_text and not result.get('description'):
                result['description'] = desc_text.strip()
        
        # Images
        img_elem = await page.query_selector('[data-qa="product-image"] img, [class*="product-image"] img, img[itemprop="image"]')
        if img_elem:
            img_src = await img_elem.get_attribute('src')
            if img_src and not result.get('images'):
                result['images'] = [img_src]
        
        # Availability
        avail_elem = await page.query_selector('[data-qa="availability"], [class*="availability"], [class*="stock-status"]')
        if avail_elem:
            avail_text = await avail_elem.inner_text()
            if avail_text:
                result['availability'] = avail_text.strip()
        
    except Exception as e:
        result['extraction_warning'] = str(e)
    
    # Check if we got any meaningful data
    if not result.get('name') and not result.get('upc'):
        result['success'] = False
        result['error'] = "Could not extract product data from page"
    
    return result


def extract_price_data(product: dict) -> dict:
    """Extract price information from product data."""
    price_info = {}
    
    # Try various price field names
    if 'price' in product:
        price_info['current'] = product['price']
    elif 'currentPrice' in product:
        price_info['current'] = product['currentPrice']
    elif 'salePrice' in product:
        price_info['current'] = product['salePrice']
    
    if 'regularPrice' in product:
        price_info['regular'] = product['regularPrice']
    elif 'originalPrice' in product:
        price_info['regular'] = product['originalPrice']
    
    if 'unitPrice' in product:
        price_info['unit'] = product['unitPrice']
    
    return price_info if price_info else None


def parse_price_text(text: str) -> dict:
    """Parse price from text like '$3.99' or '$3.99 each'."""
    price_info = {}
    
    # Find all price patterns
    prices = re.findall(r'\$?(\d+\.?\d*)', text)
    if prices:
        price_info['current'] = float(prices[0])
    
    return price_info if price_info else None


async def fetch_search_results(url: str, query: str) -> dict[str, Any]:
    """
    Fetch and parse Kroger search results using browser automation.
    """
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-http2',
            ]
        )
        
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                viewport={'width': 1920, 'height': 1080},
                geolocation={'latitude': 39.9612, 'longitude': -83.0025},
                permissions=['geolocation'],
            )
            
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)
            
            page = await context.new_page()
            
            response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            
            if not response or response.status != 200:
                return {
                    "success": False,
                    "error": f"Search request failed with status: {response.status if response else 'no response'}"
                }
            
            # Wait for search results to load
            await page.wait_for_timeout(3000)
            
            try:
                await page.wait_for_selector('[data-qa="search-result"], [class*="product-card"], [class*="search-result"]', timeout=10000)
            except:
                pass
            
            # Extract search results
            products = await extract_search_results(page)
            
            return {
                "success": True,
                "query": query,
                "url": url,
                "products": products,
                "count": len(products),
                "source": "kroger.com"
            }
            
        finally:
            await browser.close()


async def extract_search_results(page) -> list:
    """Extract product listings from search results page."""
    products = []
    
    # Try to find product cards
    product_selectors = [
        '[data-qa="search-result"]',
        '[class*="product-card"]',
        '[class*="ProductCard"]',
        '[data-testid="product-card"]',
        'article[class*="product"]'
    ]
    
    for selector in product_selectors:
        cards = await page.query_selector_all(selector)
        if cards:
            for card in cards[:20]:  # Limit to first 20 results
                try:
                    product = {}
                    
                    # Name
                    name_elem = await card.query_selector('a[href*="/p/"], h3, h2, [class*="title"], [class*="name"]')
                    if name_elem:
                        product['name'] = (await name_elem.inner_text()).strip()
                        
                        # Get link
                        href = await name_elem.get_attribute('href')
                        if href:
                            product['url'] = f"https://www.kroger.com{href}" if href.startswith('/') else href
                            # Extract UPC from URL
                            upc_match = re.search(r'/(\d{10,14})/?$', href)
                            if upc_match:
                                product['upc'] = upc_match.group(1)
                    
                    # Price
                    price_elem = await card.query_selector('[class*="price"], [data-qa="price"]')
                    if price_elem:
                        price_text = await price_elem.inner_text()
                        product['price'] = parse_price_text(price_text)
                    
                    # Image
                    img_elem = await card.query_selector('img')
                    if img_elem:
                        product['image'] = await img_elem.get_attribute('src')
                    
                    # Brand
                    brand_elem = await card.query_selector('[class*="brand"]')
                    if brand_elem:
                        product['brand'] = (await brand_elem.inner_text()).strip()
                    
                    if product.get('name') or product.get('upc'):
                        products.append(product)
                        
                except Exception:
                    continue
            
            if products:
                break
    
    return products