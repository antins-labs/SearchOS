"""
Moutai China Product Catalog Access Skill

Provides access to Moutai China's product catalog (www.moutaichina.com).
This is a static HTML site that can be scraped with direct HTTP requests.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any, Optional
from urllib.parse import urljoin
import re


BASE_URL = "https://www.moutaichina.com"

# Known category URLs
CATEGORIES = {
    "all": "/mtgf/cpzx/index.html",
    "moutai_series": "/mtgf/cpzx/mtjxl/index.html",  # 贵州茅台酒
    "jiangxiang_series": "/mtgf/cpzx/jxxlj62/index.html",  # 酱香系列酒
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


async def fetch_page(session: aiohttp.ClientSession, url: str, timeout: int = 30) -> Optional[str]:
    """Fetch a page and return HTML content"""
    try:
        full_url = urljoin(BASE_URL, url) if not url.startswith("http") else url
        async with session.get(full_url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            if response.status == 200:
                return await response.text()
            return None
    except Exception as e:
        return None


def parse_product_from_list(item) -> dict:
    """Parse a product from listing page"""
    product = {}
    
    # Product name and URL
    em = item.select_one("em")
    if em:
        product["name"] = em.get_text(strip=True)
    
    link = item.select_one("a[href*='article']")
    if link:
        href = link.get("href", "")
        product["url"] = urljoin(BASE_URL, href)
        product["id"] = href.split("/")[-1].replace(".html", "") if href else None
    
    # Product image
    img = item.select_one("img")
    if img:
        src = img.get("src", img.get("data-src", ""))
        product["image"] = urljoin(BASE_URL, src) if src else None
        product["image_alt"] = img.get("alt", "")
    
    # Product specs from listing
    desc = item.select_one(".text-desc")
    if desc:
        specs = {}
        for p in desc.select("p"):
            text = p.get_text(strip=True)
            if "：" in text:
                key, value = text.split("：", 1)
                specs[key.strip()] = value.strip()
        if specs:
            product["specs"] = specs
            # Extract common fields
            product["alcohol_content"] = specs.get("酒精含量")
            product["volume"] = specs.get("规　　格")
            product["fragrance_type"] = specs.get("香　　型")
    
    return product


def parse_product_detail(html: str) -> dict:
    """Parse product detail page"""
    soup = BeautifulSoup(html, "html.parser")
    product = {}
    
    # Product main info
    cpxxjs = soup.select_one(".cpxxjs")
    if cpxxjs:
        # Image
        cpimg = cpxxjs.select_one(".cpimg img")
        if cpimg:
            src = cpimg.get("src", "")
            product["image"] = urljoin(BASE_URL, src) if src else None
            product["image_alt"] = cpimg.get("alt", "")
        
        # Title and specs
        cpxx = cpxxjs.select_one(".cpxx")
        if cpxx:
            h2 = cpxx.select_one("h2")
            if h2:
                product["name"] = h2.get_text(strip=True)
            
            specs = {}
            for p in cpxx.select("p"):
                span = p.select_one("span")
                em = p.select_one("em")
                if span and em:
                    key = span.get_text(strip=True).replace("：", "").strip()
                    value = em.get_text(strip=True)
                    specs[key] = value
            
            product["specs"] = specs
            product["fragrance_type"] = specs.get("香型", specs.get("香　　型"))
            product["alcohol_content"] = specs.get("酒精含量")
            product["volume"] = specs.get("规格", specs.get("规　　格"))
            product["packaging_size"] = specs.get("彩盒尺寸")
            product["ingredients"] = specs.get("配料", specs.get("配　　料"))
            product["storage_conditions"] = specs.get("储存条件")
    
    # Product description
    cpms = soup.select_one(".cpms")
    if cpms:
        product["description"] = cpms.get_text(strip=True)
    
    # Breadcrumb
    breadcrumb = soup.select_one(".dqwz, .breadcrumb")
    if breadcrumb:
        product["breadcrumb"] = breadcrumb.get_text(strip=True)
    
    return product


def parse_pagination(soup: BeautifulSoup, current_path: str) -> dict:
    """Parse pagination info from page"""
    pagination = {"current_page": 1, "total_pages": 1, "total_items": 0}
    
    page_span = soup.select_one(".mt_page span")
    if page_span:
        text = page_span.get_text(strip=True)
        # Parse: 共13条记录   第1/2页
        items_match = re.search(r"共(\d+)条", text)
        if items_match:
            pagination["total_items"] = int(items_match.group(1))
        
        page_match = re.search(r"第(\d+)/(\d+)页", text)
        if page_match:
            pagination["current_page"] = int(page_match.group(1))
            pagination["total_pages"] = int(page_match.group(2))
    
    # Get page URLs
    pagination["pages"] = {}
    page_links = soup.select("a[onclick*=\".html\"]")
    for link in page_links:
        onclick = link.get("onclick", "")
        if "queryArticleByCondition" in onclick:
            match = re.search(r"['\"]([^'\"]+\d+\.html)['\"]", onclick)
            if match:
                page_url = match.group(1)
                page_num = re.search(r"-(\d+)\.html", page_url)
                if page_num:
                    pagination["pages"][int(page_num.group(1))] = urljoin(BASE_URL, page_url)
    
    return pagination


def parse_categories(html: str) -> list:
    """Parse product categories from page"""
    soup = BeautifulSoup(html, "html.parser")
    categories = []
    
    # Main category navigation
    menutwo = soup.select_one(".menutwo")
    if menutwo:
        for a in menutwo.select("a"):
            href = a.get("href", "")
            categories.append({
                "name": a.get_text(strip=True),
                "url": urljoin(BASE_URL, href),
                "is_active": "on" in a.get("class", [])
            })
    
    # Series subcategories
    series = soup.select(".mtjxl")
    for item in series:
        span = item.select_one("span")
        if span:
            series_name = span.get_text(strip=True)
            products = []
            for a in item.select("p a"):
                products.append(a.get_text(strip=True))
            if products:
                categories.append({
                    "series": series_name,
                    "products": products
                })
    
    return categories


async def list_products(session: aiohttp.ClientSession, category: str = "all", page: int = 1) -> dict:
    """List products from a category with pagination"""
    result = {
        "success": False,
        "products": [],
        "pagination": {},
        "error": None
    }
    
    # Get category URL
    cat_url = CATEGORIES.get(category, CATEGORIES["all"])
    
    # For pagination, we need to discover the pagination URL pattern from page 1
    if page > 1:
        # Fetch page 1 first to get the pagination URL pattern
        html = await fetch_page(session, cat_url)
        if not html:
            result["error"] = "Failed to fetch the first page to discover pagination"
            return result
        
        soup = BeautifulSoup(html, "html.parser")
        pagination = parse_pagination(soup, cat_url)
        
        if page in pagination.get("pages", {}):
            # Fetch the actual requested page
            cat_url = pagination["pages"][page]
            html = await fetch_page(session, cat_url)
        else:
            result["error"] = f"Page {page} not found. Total pages: {pagination.get('total_pages', 1)}"
            return result
    else:
        html = await fetch_page(session, cat_url)
    
    if not html:
        result["error"] = "Failed to fetch page"
        return result
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Parse products
    items = soup.select(".cpimgList li")
    for item in items:
        product = parse_product_from_list(item)
        if product.get("name"):
            result["products"].append(product)
    
    # Parse pagination from the fetched page
    result["pagination"] = parse_pagination(soup, cat_url)
    
    result["success"] = True
    result["category"] = category
    result["url"] = urljoin(BASE_URL, cat_url)
    
    return result


async def get_product_detail(session: aiohttp.ClientSession, url: str) -> dict:
    """Get detailed product information"""
    result = {
        "success": False,
        "product": {},
        "error": None
    }
    
    html = await fetch_page(session, url)
    if not html:
        result["error"] = "Failed to fetch product page"
        return result
    
    product = parse_product_detail(html)
    product["url"] = url
    
    result["product"] = product
    result["success"] = True
    
    return result


async def get_categories(session: aiohttp.ClientSession) -> dict:
    """Get all product categories"""
    result = {
        "success": False,
        "categories": [],
        "error": None
    }
    
    html = await fetch_page(session, CATEGORIES["all"])
    if not html:
        result["error"] = "Failed to fetch categories"
        return result
    
    result["categories"] = parse_categories(html)
    result["success"] = True
    
    return result


async def search_products(session: aiohttp.ClientSession, query: str, category: str = "all") -> dict:
    """Search products by name (client-side filtering)"""
    result = {
        "success": False,
        "query": query,
        "products": [],
        "error": None
    }
    
    # Fetch all products from category
    all_products = []
    cat_url = CATEGORIES.get(category, CATEGORIES["all"])
    
    html = await fetch_page(session, cat_url)
    if not html:
        result["error"] = "Failed to fetch products"
        return result
    
    soup = BeautifulSoup(html, "html.parser")
    
    # Get all pages
    pagination = parse_pagination(soup, cat_url)
    
    # Fetch products from all pages
    for page_num in range(1, pagination.get("total_pages", 1) + 1):
        if page_num == 1:
            page_html = html
        else:
            if page_num in pagination.get("pages", {}):
                page_html = await fetch_page(session, pagination["pages"][page_num])
            else:
                continue
        
        if page_html:
            page_soup = BeautifulSoup(page_html, "html.parser")
            items = page_soup.select(".cpimgList li")
            for item in items:
                product = parse_product_from_list(item)
                if product.get("name"):
                    all_products.append(product)
    
    # Filter by query
    query_lower = query.lower()
    for product in all_products:
        if query_lower in product.get("name", "").lower():
            result["products"].append(product)
    
    result["success"] = True
    result["total_found"] = len(result["products"])
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Moutai China access skill.
    
    Parameters:
        function: str - The function to execute:
            - 'list_products': List products from a category
            - 'get_product': Get detailed product information
            - 'get_categories': Get all product categories
            - 'search': Search products by name
        
        For list_products:
            category: str - Category key ('all', 'moutai_series', 'jiangxiang_series')
            page: int - Page number (default: 1)
        
        For get_product:
            url: str - Product detail page URL
        
        For search:
            query: str - Search query
            category: str - Optional category filter
    
    Returns:
        dict with 'success', results, and optional 'error' fields
    """
    function = params.get("function", "")
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: 'function'. Valid functions: list_products, get_product, get_categories, search"
        }
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        if function == "list_products":
            category = params.get("category", "all")
            page = params.get("page", 1)
            
            if category not in CATEGORIES:
                return {
                    "success": False,
                    "error": f"Invalid category. Valid categories: {list(CATEGORIES.keys())}"
                }
            
            return await list_products(session, category, page)
        
        elif function == "get_product":
            url = params.get("url")
            if not url:
                return {
                    "success": False,
                    "error": "Missing required parameter: 'url' for product detail"
                }
            
            return await get_product_detail(session, url)
        
        elif function == "get_categories":
            return await get_categories(session)
        
        elif function == "search":
            query = params.get("query")
            if not query:
                return {
                    "success": False,
                    "error": "Missing required parameter: 'query' for search"
                }
            
            category = params.get("category", "all")
            return await search_products(session, query, category)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: '{function}'. Valid functions: list_products, get_product, get_categories, search"
            }