"""
SearchOS access skill for www.lzlj.com
Luzhou Laojiao brand and product information scraper
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
from typing import Any, Optional


BASE_URL = "http://www.lzlj.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> tuple[Optional[str], int]:
    """Fetch HTML content from a URL, return (html, status_code)"""
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                html = await resp.text()
                return html, resp.status
            return None, resp.status
    except Exception as e:
        return None, 0


def normalize_url(url: str) -> str:
    """Normalize URL to absolute URL"""
    if url.startswith("//"):
        return "http:" + url
    elif url.startswith("/"):
        return BASE_URL + url
    elif not url.startswith("http"):
        return BASE_URL + "/" + url
    return url


def is_page_not_found(html: str, content_length: int = None) -> bool:
    """
    Check if the page is a 'not found' error page.
    The site returns 200 status for error pages, so we need to check content.
    """
    if not html:
        return True
    
    # Valid pages are typically > 10KB, error pages are small (< 5KB)
    if content_length is not None and content_length < 5000:
        # Likely an error page, but check for specific indicators
        pass
    
    # Check for specific 404 page indicators - must be exact or nearly exact
    # The error page has these specific phrases
    if "您访问的网页出错了" in html or "Page not found" in html:
        return True
    
    return False


async def list_brands(session: aiohttp.ClientSession) -> dict:
    """List all available brand categories"""
    url = f"{BASE_URL}/brand/"
    html, status = await fetch_page(session, url)
    
    if not html:
        return {"error": f"Failed to fetch brand listing page (status: {status})", "brands": []}
    
    if is_page_not_found(html, len(html)):
        return {"error": "Brand listing page not found", "brands": []}
    
    soup = BeautifulSoup(html, "html.parser")
    brands = []
    seen = set()
    
    # Find all brand links (matching pattern /brand/{slug}/)
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.get_text(strip=True)
        
        # Match brand pages: /brand/{slug}/
        match = re.search(r"/brand/([^/]+)/?$", href)
        if match and text and len(text) < 20:
            slug = match.group(1)
            # Skip numeric-only slugs or duplicates
            if slug not in seen:
                seen.add(slug)
                brands.append({
                    "name": text,
                    "slug": slug,
                    "url": normalize_url(href),
                })
    
    return {"brands": brands, "count": len(brands)}


async def list_products(session: aiohttp.ClientSession, brand_slug: str) -> dict:
    """List all products under a specific brand"""
    # Normalize slug (remove trailing slashes)
    brand_slug = brand_slug.strip("/").split("/")[-1]
    
    url = f"{BASE_URL}/brand/{brand_slug}/"
    html, status = await fetch_page(session, url)
    
    if not html:
        return {"error": f"Failed to fetch brand page for '{brand_slug}' (status: {status})", "products": []}
    
    if is_page_not_found(html, len(html)):
        return {"error": f"Brand '{brand_slug}' not found", "products": []}
    
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen = set()
    
    # Find product links with pattern /brand/{brand_slug}/{product_id}.html
    pattern = re.compile(rf"/brand/{brand_slug}/(\d+)\.html")
    
    # Look for LI items with product links (the structure uses li.wow)
    for li in soup.find_all("li", class_="wow"):
        link = li.find("a", href=True)
        if link:
            href = link["href"]
            match = pattern.search(href)
            if match and href not in seen:
                seen.add(href)
                
                # Get product name from <p> tag inside
                name_p = link.find("p")
                name = name_p.get_text(strip=True) if name_p else ""
                
                # Get product image
                img = link.find("img")
                img_src = normalize_url(img["src"]) if img and img.get("src") else None
                
                # Get product ID from URL
                product_id = match.group(1)
                
                products.append({
                    "id": product_id,
                    "name": name,
                    "url": normalize_url(href),
                    "image": img_src,
                })
    
    # Fallback: if no products found via LI items, try direct link extraction
    if not products:
        for link in soup.find_all("a", href=True):
            href = link["href"]
            match = pattern.search(href)
            if match and href not in seen:
                seen.add(href)
                name = link.get_text(strip=True)
                img = link.find("img")
                img_src = normalize_url(img["src"]) if img and img.get("src") else None
                product_id = match.group(1)
                
                products.append({
                    "id": product_id,
                    "name": name,
                    "url": normalize_url(href),
                    "image": img_src,
                })
    
    # Get brand intro text if available
    brand_intro = None
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text and len(text) > 50 and ("国宝" in text or "窖池" in text or "1573" in text or "浓香" in text):
            brand_intro = text
            break
    
    return {
        "brand_slug": brand_slug,
        "brand_intro": brand_intro,
        "products": products,
        "count": len(products),
    }


async def get_product_detail(session: aiohttp.ClientSession, product_url: str) -> dict:
    """Get detailed information about a specific product"""
    # Normalize URL
    if not product_url.startswith("http"):
        product_url = normalize_url(product_url)
    
    html, status = await fetch_page(session, product_url)
    
    if not html:
        return {"error": f"Failed to fetch product page: {product_url} (status: {status})"}
    
    if is_page_not_found(html, len(html)):
        return {"error": f"Product page not found: {product_url}"}
    
    soup = BeautifulSoup(html, "html.parser")
    
    result = {
        "url": product_url,
        "name": None,
        "introduction": None,
        "specifications": {},
        "images": [],
    }
    
    # Extract product name from h3 tag
    # The site uses h3 for product name in the main content
    h3_tags = soup.find_all("h3")
    for h3 in h3_tags:
        text = h3.get_text(strip=True)
        # Product names usually contain brand name or numbers
        if text and len(text) < 50 and ("国窖" in text or "泸州老窖" in text or "1573" in text or any(kw in text for kw in ["特曲", "曲", "窖", "酒"])):
            result["name"] = text
            break
    
    # Extract product introduction from p tag
    # Look for the first substantial paragraph with relevant keywords
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text and len(text) > 50:
            # Check if this is the product intro (contains brand/product info)
            if any(kw in text for kw in ["源自", "国宝", "窖池", "酿造", "酒品", "浓香"]):
                result["introduction"] = text
                break
    
    # Extract specifications from specs-item elements
    for item in soup.find_all(class_="specs-item"):
        label_elem = item.select_one(".specs-t")
        value_elem = item.select_one(".specs-b")
        if label_elem and value_elem:
            label = label_elem.get_text(strip=True)
            value = value_elem.get_text(strip=True)
            result["specifications"][label] = value
    
    # Extract product images
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if "upload" in src and any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
            result["images"].append(normalize_url(src))
    
    # Extract banner image (main product image)
    banner = soup.select_one(".site_banner img, .brandDel_img img, .banner img")
    if banner and banner.get("src"):
        banner_src = normalize_url(banner["src"])
        if banner_src not in result["images"]:
            result["images"].insert(0, banner_src)
    
    # Get meta description if available
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        result["meta_description"] = meta_desc["content"]
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the SearchOS skill
    
    Args:
        params: Dictionary containing:
            - function: Required. One of "list_brands", "list_products", "get_product_detail"
            - brand_slug: Required for list_products
            - product_url: Required for get_product_detail
        ctx: Optional context (unused)
    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function")
    
    if not function:
        return {"error": "Missing required parameter: function. Must be one of: list_brands, list_products, get_product_detail"}
    
    async with aiohttp.ClientSession() as session:
        if function == "list_brands":
            return await list_brands(session)
        
        elif function == "list_products":
            brand_slug = params.get("brand_slug")
            if not brand_slug:
                return {"error": "Missing required parameter: brand_slug for list_products function"}
            return await list_products(session, brand_slug)
        
        elif function == "get_product_detail":
            product_url = params.get("product_url")
            if not product_url:
                return {"error": "Missing required parameter: product_url for get_product_detail function"}
            return await get_product_detail(session, product_url)
        
        else:
            return {"error": f"Unknown function: {function}. Must be one of: list_brands, list_products, get_product_detail"}


# For testing
if __name__ == "__main__":
    async def test():
        print("Testing list_brands...")
        result = await execute({"function": "list_brands"})
        print(f"Found {result.get('count', 0)} brands")
        for brand in result.get("brands", [])[:5]:
            print(f"  - {brand['name']}: {brand['slug']}")
        
        print("\nTesting list_products for brand '1573'...")
        result = await execute({"function": "list_products", "brand_slug": "1573"})
        print(f"Found {result.get('count', 0)} products")
        for product in result.get("products", [])[:5]:
            print(f"  - {product['name']}: {product['id']}")
        
        print("\nTesting get_product_detail...")
        product_url = "http://www.lzlj.com/brand/1573/3742.html"
        result = await execute({"function": "get_product_detail", "product_url": product_url})
        print(f"Name: {result.get('name')}")
        print(f"Introduction: {result.get('introduction', '')[:100]}...")
        print(f"Specifications: {result.get('specifications')}")
        print(f"Images: {len(result.get('images', []))} found")
    
    asyncio.run(test())