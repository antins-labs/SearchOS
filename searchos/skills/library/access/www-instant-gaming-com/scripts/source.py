"""
Instant Gaming Product Page Access Skill

Fetches product information from Instant Gaming product pages including:
- Product title, image, and description
- Current price, original price, and discount percentage
- Availability/stock status
- Platform (Steam, Epic Games, etc.)
- Region options and their prices
- Product metadata (SKU, category, publisher)
"""

from typing import Any
import asyncio
import re


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Instant Gaming product page scraper.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ('get_product_info')
            - url: The Instant Gaming product page URL

    
    Returns:
        Dictionary with product information or error details
    """
    function = params.get("function", "")
    
    if function == "get_product_info":
        return await get_product_info(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_product_info"]
        }


async def get_product_info(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch product information from an Instant Gaming product page.
    
    Args:
        params: Must contain 'url' with the product page URL

    
    Returns:
        Dictionary with product data including:
        - title, display_title, url, image, description
        - current_price, original_price, discount_percent
        - price_numeric, original_price_numeric
        - currency
        - in_stock, stock_text
        - platform, platform_icon
        - regions (list of region options with prices)
        - sku, category, publisher
        - availability
    """
    url = params.get("url", "")
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url"
        }
    
    # Validate URL
    if not url.startswith("https://www.instant-gaming.com/"):
        return {
            "success": False,
            "error": "Invalid URL: must be from www.instant-gaming.com"
        }
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()
                
                # Navigate to the page
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                    await page.wait_for_timeout(3000)  # Wait for dynamic content
                except Exception as e:
                    # Try to continue even if timeout occurs
                    pass
                
                # Extract product data
                data = await page.evaluate('''() => {
                    const result = {};
                    
                    // Helper to get meta content
                    const getMeta = (name) => {
                        const meta = document.querySelector(`meta[property="${name}"], meta[name="${name}"], meta[itemprop="${name}"]`);
                        return meta ? meta.getAttribute('content') : null;
                    };
                    
                    // Get basic info from meta tags
                    result.title = getMeta('og:title');
                    result.url = getMeta('og:url') || window.location.href;
                    result.image = getMeta('og:image');
                    result.sku = getMeta('sku');
                    result.category = getMeta('category');
                    result.platform = getMeta('gamePlatform');
                    result.publisher = getMeta('publisher') || getMeta('author');
                    result.price = getMeta('price');
                    result.priceCurrency = getMeta('priceCurrency');
                    result.availability = getMeta('availability');
                    result.description = getMeta('description');
                    
                    // Get main product panel
                    const panel = document.querySelector('.panel.item, .panel-header');
                    if (panel) {
                        // Title from H1
                        const h1 = panel.querySelector('h1');
                        if (h1) result.displayTitle = h1.innerText.trim();
                        
                        // Platform
                        const platformEl = panel.querySelector('.platform-container, .platforms');
                        if (platformEl) {
                            const platformText = platformEl.querySelector('span');
                            const platformIcon = platformEl.querySelector('[class*="icon-"]');
                            result.platformDisplay = platformText ? platformText.innerText.trim() : null;
                            result.platformIcon = platformIcon ? platformIcon.className : null;
                        }
                        
                        // Stock status
                        const stockEl = panel.querySelector('.stock');
                        if (stockEl) {
                            result.stockText = stockEl.innerText.trim();
                            result.inStock = result.stockText.toLowerCase().includes('in stock');
                        }
                        
                        // Digital download
                        const downloadEl = panel.querySelector('.download');
                        if (downloadEl) {
                            result.digitalDownload = downloadEl.innerText.trim().toLowerCase().includes('digital download');
                        }
                        
                        // Original price
                        const retailEl = panel.querySelector('.discounts .retail');
                        if (retailEl) {
                            result.originalPrice = retailEl.innerText.trim();
                        }
                        
                        // Discount percentage
                        const discountEl = panel.querySelector('.discounted');
                        if (discountEl) {
                            const discountText = discountEl.innerText.trim();
                            const match = discountText.match(/-?\\d+/);
                            result.discountPercent = match ? parseInt(match[0]) : null;
                        }
                        
                        // Current price
                        const totalEl = panel.querySelector('.total');
                        if (totalEl) {
                            result.currentPrice = totalEl.innerText.trim();
                        }
                        
                        // Region options
                        const regionSelect = panel.querySelector('.regions');
                        if (regionSelect) {
                            const options = regionSelect.querySelectorAll('option');
                            result.regions = [];
                            options.forEach(opt => {
                                result.regions.push({
                                    name: opt.innerText.trim(),
                                    value: opt.value,
                                    price: opt.getAttribute('data-product-price'),
                                    href: opt.getAttribute('data-href')
                                });
                            });
                        }
                    }
                    
                    return result;
                }''')
                
                # Process and clean up the data
                product = {
                    "success": True,
                    "title": data.get("title"),
                    "display_title": data.get("displayTitle"),
                    "url": data.get("url"),
                    "image": data.get("image"),
                    "description": data.get("description"),
                    "current_price": data.get("currentPrice"),
                    "original_price": data.get("originalPrice"),
                    "discount_percent": data.get("discountPercent"),
                    "currency": data.get("priceCurrency"),
                    "in_stock": data.get("inStock", False),
                    "stock_text": data.get("stockText"),
                    "platform": data.get("platform") or data.get("platformDisplay"),
                    "platform_icon": data.get("platformIcon"),
                    "sku": data.get("sku"),
                    "category": data.get("category"),
                    "publisher": data.get("publisher"),
                    "availability": data.get("availability"),
                    "digital_download": data.get("digitalDownload", False),
                    "regions": data.get("regions", [])
                }
                
                # Extract numeric prices for easier use
                if product["current_price"]:
                    price_match = re.search(r'[\d.]+', product["current_price"].replace(',', ''))
                    if price_match:
                        product["price_numeric"] = float(price_match.group())
                
                if product["original_price"]:
                    orig_match = re.search(r'[\d.]+', product["original_price"].replace(',', ''))
                    if orig_match:
                        product["original_price_numeric"] = float(orig_match.group())
                
                # Use meta price if current_price not found
                if not product["current_price"] and data.get("price"):
                    product["current_price"] = f"${data['price']}"
                    try:
                        product["price_numeric"] = float(data["price"])
                    except:
                        pass
                
                return product
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch product: {str(e)}"
        }