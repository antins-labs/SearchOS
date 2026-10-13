"""
access-skill: Graduate Admission Score Lines (研究生招生分数线)
Host: yz.chsi.com.cn (China Graduate Admission Information Network)

This skill provides access to Chinese graduate admission score line data including:
- 34 self-determined score line universities
- National minimum admission score lines by year
- Schools by province with score query capabilities
- Score line detail pages (images and PDF downloads)
"""

import re
import json
import urllib.parse
from typing import Any, Optional
import httpx
from bs4 import BeautifulSoup


BASE_URL = "https://yz.chsi.com.cn"
PROVINCE_API = "https://yz.chsi.com.cn/apply/code/cjcxshouyedw/{code}.json"

# Province codes (from the embedded data)
PROVINCE_CODES = {
    "北京": "11",
    "天津": "12",
    "河北": "13",
    "山西": "14",
    "内蒙古": "15",
    "辽宁": "21",
    "吉林": "22",
    "黑龙江": "23",
    "上海": "31",
    "江苏": "32",
    "浙江": "33",
    "安徽": "34",
    "福建": "35",
    "江西": "36",
    "山东": "37",
    "河南": "41",
    "湖北": "42",
    "湖南": "43",
    "广东": "44",
    "广西": "45",
    "海南": "46",
    "重庆": "50",
    "四川": "51",
    "贵州": "52",
    "云南": "53",
    "西藏": "54",
    "陕西": "61",
    "甘肃": "62",
    "青海": "63",
    "宁夏": "64",
    "新疆": "65",
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _make_client() -> httpx.AsyncClient:
    """Create an async HTTP client with proper configuration."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )


async def _fetch_page(url: str) -> dict[str, Any]:
    """Fetch an HTML page and return structured data."""
    async with _make_client() as client:
        try:
            response = await client.get(url, headers={**DEFAULT_HEADERS, "Referer": BASE_URL})
            response.raise_for_status()
            return {
                "success": True,
                "html": response.text,
                "url": str(response.url),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "url": url}


async def _fetch_json(url: str) -> dict[str, Any]:
    """Fetch JSON data from an API endpoint."""
    async with _make_client() as client:
        try:
            response = await client.get(url, headers={**DEFAULT_HEADERS, "Referer": BASE_URL})
            response.raise_for_status()
            data = response.json()
            return {"success": True, "data": data, "url": str(response.url)}
        except Exception as e:
            return {"success": False, "error": str(e), "url": url}


def _extract_javascript_array(html: str, var_name: str) -> list[dict]:
    """Extract a JavaScript array variable from HTML page."""
    
    # Pattern to find the variable assignment
    pattern = rf'var\s+{var_name}\s*=\s*(\[[\s\S]*?\n\s*\]);'
    match = re.search(pattern, html)
    
    if not match:
        # Try Vue data pattern
        pattern = rf'{var_name}\s*:\s*(\[[\s\S]*?\n\s*\])'
        match = re.search(pattern, html)
    
    if not match:
        return []
    
    json_str = match.group(1)
    
    # Find balanced brackets
    bracket_count = 0
    in_string = False
    end_pos = 0
    
    for i, c in enumerate(json_str):
        if c == '"' and (i == 0 or json_str[i-1] != '\\'):
            in_string = not in_string
        if not in_string:
            if c == '[':
                bracket_count += 1
            elif c == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    end_pos = i + 1
                    break
    
    json_str = json_str[:end_pos]
    
    # Convert JavaScript to JSON
    # Quote unquoted keys
    json_str = re.sub(r"'", '"', json_str)  # Single to double quotes
    json_str = re.sub(r'(\w+)\s*:', r'"\1":', json_str)
    
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return []


async def list_34_universities(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List all 34 self-determined score line universities with their historical score line URLs.
    
    These 34 universities are authorized to set their own admission score lines independently
    from the national minimum scores.
    
    Args:
        params: Optional filters:
            - university: Filter by university name (partial match)
            - year: Filter by year (e.g., "2025")
    
    Returns:
        Dictionary containing list of universities with their score line URLs by year.
    """
    url = "https://yz.chsi.com.cn/kyzx/zt/kyfs2025.shtml"
    result = await _fetch_page(url)
    
    if not result["success"]:
        return {"success": False, "error": result["error"], "universities": []}
    
    universities = _extract_javascript_array(result["html"], "zhxList")
    
    if not universities:
        return {
            "success": False,
            "error": "Failed to extract university data from page",
            "universities": [],
        }
    
    # Apply filters
    filtered_unis = []
    filter_uni = params.get("university", "").lower()
    filter_year = str(params.get("year", ""))
    
    for uni in universities:
        uni_name = uni.get("yxmc", "")
        year_list = uni.get("yearList", [])
        
        if filter_uni and filter_uni not in uni_name.lower():
            continue
        
        year_urls = year_list
        if filter_year:
            year_urls = [y for y in year_list if str(y.get("year")) == filter_year]
            if not year_urls:
                continue
        
        filtered_unis.append({
            "university": uni_name,
            "years": [
                {
                    "year": y.get("year"),
                    "url": BASE_URL + y.get("url", "") if y.get("url", "").startswith("/") else y.get("url", ""),
                }
                for y in year_urls
            ],
        })
    
    return {
        "success": True,
        "total": len(filtered_unis),
        "universities": filtered_unis,
        "source_url": url,
    }


async def list_national_lines(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List national minimum admission score lines by year.
    
    These are the minimum scores set by the Ministry of Education that all graduate
    admission candidates must meet for复试 (re-examination/interview round).
    
    Args:
        params: Optional filter by year
    
    Returns:
        Dictionary containing list of national score line URLs by year.
    """
    url = "https://yz.chsi.com.cn/kyzx/zt/kyfs2025.shtml"
    result = await _fetch_page(url)
    
    if not result["success"]:
        return {"success": False, "error": result["error"], "years": []}
    
    year_list = _extract_javascript_array(result["html"], "yearList")
    
    if not year_list:
        return {
            "success": False,
            "error": "Failed to extract national line data from page",
            "years": [],
        }
    
    filter_year = str(params.get("year", ""))
    
    years = []
    for item in year_list:
        year = str(item.get("year", ""))
        
        if filter_year and year != filter_year:
            continue
        
        url_path = item.get("url", "")
        full_url = BASE_URL + url_path if url_path.startswith("/") else url_path
        
        years.append({
            "year": year,
            "url": full_url,
        })
    
    return {
        "success": True,
        "total": len(years),
        "years": years,
        "source_url": url,
    }


async def list_provinces(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    List all provinces/regions for school lookup.
    
    Use these province codes to query schools in each province by using
    get_schools_by_province function.
    
    Args:
        params: No parameters required
    
    Returns:
        Dictionary containing list of provinces with their codes.
    """
    provinces = [
        {"code": code, "name": name}
        for name, code in sorted(PROVINCE_CODES.items(), key=lambda x: int(x[1]))
    ]
    
    return {
        "success": True,
        "total": len(provinces),
        "provinces": provinces,
        "usage": "Use get_schools_by_province with province code to get school list",
    }


async def get_schools_by_province(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get schools in a province for score query.
    
    Args:
        params: Must contain:
            - province_code: Province code (e.g., "11" for Beijing)
            OR
            - province_name: Province name in Chinese (e.g., "北京")
    
    Returns:
        Dictionary containing list of schools in the province with their details:
        - dwdm: Institution code
        - dwmc: Institution name
        - schurl: Institution website URL (if available)
        - cxfs: Query method ("chsi" = query on this site, "sch" = query on school site)
        - needlogin: Whether login is required
    """
    province_code = params.get("province_code")
    province_name = params.get("province_name")
    
    if not province_code and province_name:
        province_code = PROVINCE_CODES.get(province_name)
    
    if not province_code:
        return {
            "success": False,
            "error": "province_code or province_name is required",
            "valid_provinces": list(PROVINCE_CODES.keys()),
            "schools": [],
        }
    
    url = PROVINCE_API.format(code=province_code)
    result = await _fetch_json(url)
    
    if not result["success"]:
        return {"success": False, "error": result["error"], "schools": []}
    
    data = result.get("data", {})
    schools = data.get("dms", [])
    
    # Find province name
    province_display = province_name or next(
        (name for name, code in PROVINCE_CODES.items() if code == province_code),
        province_code
    )
    
    return {
        "success": True,
        "province_code": province_code,
        "province_name": province_display,
        "total": len(schools),
        "schools": [
            {
                "code": s.get("dwdm"),
                "name": s.get("dwmc"),
                "website": s.get("schurl") or None,
                "query_method": "此站查询" if s.get("cxfs") == "chsi" else "院校官网查询",
                "login_required": s.get("needlogin") == "1",
            }
            for s in schools
        ],
        "source_url": url,
    }


async def get_score_line_detail(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Get detailed content of a score line page.
    
    Score line pages typically contain images of score tables and/or PDF download links.
    Important: The actual score tables are embedded as images, not HTML tables.
    
    Args:
        params: Must contain:
            - url: URL of the score line page (e.g., from list_34_universities or list_national_lines)
    
    Returns:
        Dictionary containing:
        - title: Page title
        - images: List of score table images
        - pdf_links: PDF download links
        - text: Text content
        - article_id: Article ID for reference
    """
    url = params.get("url")
    
    if not url:
        return {
            "success": False,
            "error": "url parameter is required",
            "detail": None,
        }
    
    # Ensure URL is absolute
    if url.startswith("/"):
        url = BASE_URL + url
    
    result = await _fetch_page(url)
    
    if not result["success"]:
        return {"success": False, "error": result["error"], "detail": None}
    
    html = result["html"]
    soup = BeautifulSoup(html, "html.parser")
    
    # Extract title
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None
    
    # Extract article content
    article = soup.find("div", id="article_dnull")
    if not article:
        article = soup.find("div", class_="article-con")
    
    images = []
    pdf_links = []
    text_content = ""
    
    if article:
        # Extract images
        for img in article.find_all("img"):
            img_src = img.get("src") or img.get("_src")
            if img_src:
                # Ensure absolute URL
                if img_src.startswith("//"):
                    img_src = "https:" + img_src
                elif not img_src.startswith("http"):
                    img_src = BASE_URL + img_src
                
                img_alt = img.get("alt", img.get("title", ""))
                images.append({
                    "url": img_src,
                    "alt": img_alt,
                })
        
        # Extract PDF links
        for link in article.find_all("a", href=True):
            href = link["href"]
            if ".pdf" in href.lower() or "getfile" in href.lower():
                if href.startswith("/"):
                    href = BASE_URL + href
                pdf_links.append({
                    "url": href,
                    "text": link.get_text(strip=True),
                })
        
        # Extract text
        text_content = article.get_text(separator="\n", strip=True)
    
    # Extract article ID from URL
    article_id_match = re.search(r"/(\d+)\.html$", url)
    article_id = article_id_match.group(1) if article_id_match else None
    
    # Extract publish time and source if available
    publish_time = None
    source = None
    
    time_tag = soup.find("span", class_="time") or soup.find("time")
    if time_tag:
        publish_time = time_tag.get_text(strip=True)
    
    source_tag = soup.find("span", class_="source")
    if source_tag:
        source = source_tag.get_text(strip=True)
    
    # Extract keywords from meta tags
    keywords = []
    keywords_meta = soup.find("meta", attrs={"name": "keywords"})
    if keywords_meta and keywords_meta.get("content"):
        keywords = [k.strip() for k in keywords_meta["content"].split(",") if k.strip()]
    
    return {
        "success": True,
        "detail": {
            "title": title,
            "url": url,
            "article_id": article_id,
            "publish_time": publish_time,
            "source": source,
            "images": images,
            "pdf_links": pdf_links,
            "text": text_content,
            "keywords": keywords,
            "note": "Score tables are typically embedded as images. Download the image URLs to view the actual scores.",
        },
    }


async def search_universities(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Search for universities by name across all provinces.
    
    This helper function searches for a university name and returns matching schools
    with their province information.
    
    Args:
        params: Must contain:
            - name: University name to search for (partial match supported)
    
    Returns:
        Dictionary containing list of matching schools.
    """
    name = params.get("name", "").lower()
    
    if not name:
        return {
            "success": False,
            "error": "name parameter is required",
            "results": [],
        }
    
    results = []
    
    async with _make_client() as client:
        for prov_name, prov_code in PROVINCE_CODES.items():
            try:
                url = PROVINCE_API.format(code=prov_code)
                response = await client.get(url, headers={**DEFAULT_HEADERS, "Referer": BASE_URL})
                response.raise_for_status()
                data = response.json()
                
                for school in data.get("dms", []):
                    school_name = school.get("dwmc", "")
                    if name in school_name.lower():
                        results.append({
                            "code": school.get("dwdm"),
                            "name": school_name,
                            "province": prov_name,
                            "province_code": prov_code,
                            "website": school.get("schurl") or None,
                            "query_method": "此站查询" if school.get("cxfs") == "chsi" else "院校官网查询",
                        })
            except Exception:
                continue
    
    return {
        "success": True,
        "query": name,
        "total": len(results),
        "results": results,
    }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Graduate Admission Score Lines skill.
    
    Supported functions:
    
    1. list_34_universities
       List all 34 self-determined score line universities
       Optional params: university (filter by name), year (filter by year)
    
    2. list_national_lines
       List national minimum score lines by year
       Optional params: year (filter by year)
    
    3. list_provinces
       List all provinces with their codes
    
    4. get_schools_by_province
       Get schools in a province
       Required params: province_code OR province_name
    
    5. get_score_line_detail
       Get detail of a score line page
       Required params: url
    
    6. search_universities
       Search for universities by name across all provinces
       Required params: name
    
    Returns:
        Dictionary with success status and results or error message.
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "function parameter is required",
            "available_functions": [
                "list_34_universities",
                "list_national_lines",
                "list_provinces",
                "get_schools_by_province",
                "get_score_line_detail",
                "search_universities",
            ],
        }
    
    functions = {
        "list_34_universities": list_34_universities,
        "list_national_lines": list_national_lines,
        "list_provinces": list_provinces,
        "get_schools_by_province": get_schools_by_province,
        "get_score_line_detail": get_score_line_detail,
        "search_universities": search_universities,
    }
    
    func = functions.get(function)
    if not func:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": list(functions.keys()),
        }
    
    return await func(params, ctx)


# For testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("Testing list_34_universities...")
        result = await execute({"function": "list_34_universities"})
        print(f"Success: {result['success']}")
        print(f"Total universities: {result.get('total', 0)}")
        if result['success'] and result['universities']:
            print(f"First university: {result['universities'][0]}")
        
        print("\nTesting list_national_lines...")
        result = await execute({"function": "list_national_lines"})
        print(f"Success: {result['success']}")
        print(f"Total years: {result.get('total', 0)}")
        
        print("\nTesting list_provinces...")
        result = await execute({"function": "list_provinces"})
        print(f"Success: {result['success']}")
        print(f"Total provinces: {result.get('total', 0)}")
        
        print("\nTesting get_schools_by_province...")
        result = await execute({"function": "get_schools_by_province", "province_name": "北京"})
        print(f"Success: {result['success']}")
        print(f"Total schools: {result.get('total', 0)}")
        if result['success'] and result['schools']:
            print(f"First 3 schools: {result['schools'][:3]}")
        
        print("\nTesting get_score_line_detail...")
        result = await execute({
            "function": "get_score_line_detail",
            "url": "https://yz.chsi.com.cn/kyzx/fsfsx34/202503/20250312/2293356009.html"
        })
        print(f"Success: {result['success']}")
        if result['success']:
            detail = result['detail']
            print(f"Title: {detail['title']}")
            print(f"Images: {len(detail['images'])}")
            print(f"PDF links: {len(detail['pdf_links'])}")
        
        print("\nTesting search_universities...")
        result = await execute({"function": "search_universities", "name": "北京"})
        print(f"Success: {result['success']}")
        print(f"Total matches: {result.get('total', 0)}")
        if result['success'] and result['results']:
            print(f"First 3 matches: {result['results'][:3]}")
    
    asyncio.run(test())