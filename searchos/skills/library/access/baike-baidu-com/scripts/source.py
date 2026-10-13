"""
SearchOS Access Skill for Baidu Baike (百度百科)

This skill provides access to Baidu Baike - China's largest encyclopedia.
It can search for lemmas, extract infobox data including movie metadata,
and retrieve structured information from encyclopedia entries.

Note: This site requires browser automation due to JavaScript-rendered content.
"""

import asyncio
import re
import json
import urllib.parse
from typing import Any, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


async def _init_browser() -> tuple[Browser, BrowserContext]:
    """Initialize browser context with proper headers."""
    browser = await async_playwright().start()
    chromium = await browser.chromium.launch(headless=True)
    context = await chromium.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="zh-CN",
        viewport={"width": 1920, "height": 1080}
    )
    return browser, context


async def _scrape_lemma_page(context: BrowserContext, url: str) -> dict[str, Any]:
    """
    Scrape a Baidu Baike lemma page and extract structured data.
    
    Args:
        context: Playwright browser context
        url: Full URL to the lemma page
        
    Returns:
        Dictionary containing lemma data or error information
    """
    result = {
        "success": False,
        "error": None,
        "lemma_id": None,
        "title": None,
        "description": None,
        "infobox": {},
        "summary": "",
        "url": url
    }
    
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)  # Wait for dynamic content
        
        # Check for error page
        current_url = page.url
        if "error.html" in current_url or "status=404" in current_url:
            result["error"] = "Lemma not found (404)"
            await page.close()
            return result
        
        html = await page.content()
        
        # Extract PAGE_DATA from script tag
        match = re.search(r'window\.PAGE_DATA\s*=\s*(\{.+?\});?\s*</script>', html, re.DOTALL)
        if match:
            try:
                page_data = json.loads(match.group(1))
                result["title"] = page_data.get("lemmaTitle")
                result["description"] = page_data.get("lemmaDesc")
                result["lemma_id"] = page_data.get("lemmaId")
            except json.JSONDecodeError:
                pass
        
        # Use BeautifulSoup for HTML parsing
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract infobox data (basic info table)
        basic_info = soup.find("div", class_=lambda x: x and "basicInfo" in str(x))
        if basic_info:
            dts = basic_info.find_all("dt", class_=lambda x: x and "itemName" in str(x))
            for dt in dts:
                key = dt.get_text(strip=True)
                # Remove all non-breaking spaces and extra spaces
                key = key.replace("\xa0", "")
                key = re.sub(r'\s+', '', key)  # Remove all spaces
                
                dd = dt.find_next_sibling("dd")
                if dd:
                    value = dd.get_text(strip=True)
                    # Remove reference markers like [53] or [55-56]
                    value = re.sub(r'\[\d+(?:-\d+)?\]', '', value)
                    # Clean up whitespace but preserve content spaces
                    value = re.sub(r'\s+', ' ', value).strip()
                    
                    if key and value:
                        result["infobox"][key] = value
        
        # Extract summary
        summary_div = soup.find("div", class_=lambda x: x and ("lemmaSummary" in str(x) or "largeSummary" in str(x)))
        if summary_div:
            summary = summary_div.get_text(strip=True)
            # Remove trailing collapsed content markers
            if "..." in summary and ">>>" in summary:
                summary = summary.split("...>>>")[0].strip()
            result["summary"] = summary
        
        # If title not found in PAGE_DATA, try to extract from page
        if not result["title"]:
            title_elem = soup.find("h1") or soup.find("dd", class_=lambda x: x and "lemmaTitle" in str(x))
            if title_elem:
                result["title"] = title_elem.get_text(strip=True)
        
        result["success"] = True
        
    except asyncio.TimeoutError:
        result["error"] = "Page load timeout"
    except Exception as e:
        result["error"] = f"Scraping error: {str(e)}"
    finally:
        await page.close()
    
    return result


async def _search_lemma(context: BrowserContext, keyword: str) -> dict[str, Any]:
    """
    Search for a lemma by keyword.
    
    Args:
        context: Playwright browser context
        keyword: Search keyword
        
    Returns:
        Dictionary with search results including redirect URL
    """
    result = {
        "success": False,
        "error": None,
        "keyword": keyword,
        "redirect_url": None,
        "lemma_data": None
    }
    
    page = await context.new_page()
    
    try:
        # Use Baidu Baike search redirect endpoint
        search_url = f"https://baike.baidu.com/search/word?word={urllib.parse.quote(keyword)}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(1)
        
        # Check final URL after redirects
        current_url = page.url
        
        if "error.html" in current_url:
            result["error"] = "No results found"
            await page.close()
            return result
        
        result["redirect_url"] = current_url
        result["success"] = True
        
        # If we got a valid lemma page, scrape it
        if "/item/" in current_url:
            html = await page.content()
            
            # Extract PAGE_DATA
            match = re.search(r'window\.PAGE_DATA\s*=\s*(\{.+?\});?\s*</script>', html, re.DOTALL)
            if match:
                try:
                    page_data = json.loads(match.group(1))
                    result["lemma_data"] = {
                        "lemma_id": page_data.get("lemmaId"),
                        "title": page_data.get("lemmaTitle"),
                        "description": page_data.get("lemmaDesc")
                    }
                except json.JSONDecodeError:
                    pass
        
    except asyncio.TimeoutError:
        result["error"] = "Search timeout"
    except Exception as e:
        result["error"] = f"Search error: {str(e)}"
    finally:
        await page.close()
    
    return result


async def search(params: dict[str, Any], context: Optional[BrowserContext] = None) -> dict[str, Any]:
    """
    Search for lemmas in Baidu Baike.
    
    Parameters:
        params: Dictionary containing:
            - keyword (str, required): Search keyword
        context: Optional Playwright browser context
    
    Returns:
        Dictionary with search results
    """
    keyword = params.get("keyword")
    if not keyword:
        return {
            "success": False,
            "error": "Missing required parameter: keyword",
            "results": []
        }
    
    browser = None
    own_context = False
    
    try:
        if context is None:
            browser, context = await _init_browser()
            own_context = True
        
        result = await _search_lemma(context, keyword)
        
        return {
            "success": result["success"],
            "error": result.get("error"),
            "keyword": keyword,
            "redirect_url": result.get("redirect_url"),
            "lemma_data": result.get("lemma_data"),
            "results": [{
                "title": result.get("lemma_data", {}).get("title"),
                "url": result.get("redirect_url"),
                "lemma_id": result.get("lemma_data", {}).get("lemma_id"),
                "description": result.get("lemma_data", {}).get("description")
            }] if result.get("lemma_data") else []
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "keyword": keyword,
            "results": []
        }
    
    finally:
        if own_context and browser:
            await browser.stop()


async def get_lemma(params: dict[str, Any], context: Optional[BrowserContext] = None) -> dict[str, Any]:
    """
    Get detailed information about a lemma.
    
    Parameters:
        params: Dictionary containing:
            - url (str): Full URL to the lemma page (e.g., https://baike.baidu.com/item/八佰)
            OR
            - lemma_id (str/int): Lemma ID (e.g., 20785278)
            OR
            - keyword (str): Search keyword to find the lemma
    
    Returns:
        Dictionary containing lemma data including infobox metadata
    """
    url = params.get("url")
    lemma_id = params.get("lemma_id")
    keyword = params.get("keyword")
    
    if not url and not lemma_id and not keyword:
        return {
            "success": False,
            "error": "Missing required parameter: url, lemma_id, or keyword"
        }
    
    browser = None
    own_context = False
    
    try:
        if context is None:
            browser, context = await _init_browser()
            own_context = True
        
        # Determine URL
        if url:
            target_url = url
        elif lemma_id:
            # Try to construct URL from lemma_id (we'd need to search for it)
            # For now, return an error
            return {
                "success": False,
                "error": "lemma_id parameter requires searching first. Use keyword or url instead."
            }
        else:
            # Search by keyword
            search_result = await _search_lemma(context, keyword)
            if not search_result["success"]:
                return {
                    "success": False,
                    "error": search_result.get("error", "Search failed"),
                    "keyword": keyword
                }
            target_url = search_result["redirect_url"]
        
        # Scrape the lemma page
        result = await _scrape_lemma_page(context, target_url)
        
        return result
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url,
            "lemma_id": lemma_id,
            "keyword": keyword
        }
    
    finally:
        if own_context and browser:
            await browser.stop()


async def get_movie_info(params: dict[str, Any], context: Optional[BrowserContext] = None) -> dict[str, Any]:
    """
    Get movie-specific information from a lemma page.
    
    This is a convenience function that extracts common movie metadata fields.
    
    Parameters:
        params: Dictionary containing:
            - keyword (str): Movie title or search keyword
            OR
            - url (str): Full URL to the movie lemma page
    
    Returns:
        Dictionary containing movie-specific metadata including:
        - Basic info (title, director, cast, etc.)
        - Box office
        - Release date
        - Runtime
        - etc.
    """
    result = await get_lemma(params, context)
    
    if not result.get("success"):
        return result
    
    # Extract movie-specific fields from infobox
    infobox = result.get("infobox", {})
    
    # Common Chinese field names for movies
    # Keys are stripped of all spaces
    field_mapping = {
        "中文名": "title_cn",
        "外文名": "title_en",
        "其他译名": "other_titles",
        "类型": "genre",
        "出品公司": "production_company",
        "制片地区": "production_region",
        "拍摄日期": "filming_date",
        "拍摄地点": "filming_location",
        "导演": "director",
        "编剧": "screenwriter",
        "制片人": "producer",
        "主演": "starring",
        "片长": "runtime",
        "上映时间": "release_date",
        "票房": "box_office",
        "对白语言": "language",
        "色彩": "color",
        "imdb编码": "imdb_id",
        "在线播放平台": "streaming_platform"
    }
    
    movie_info = {
        "success": True,
        "title": result.get("title"),
        "description": result.get("description"),
        "lemma_id": result.get("lemma_id"),
        "url": result.get("url"),
        "summary": result.get("summary"),
    }
    
    # Map infobox fields to English keys
    for cn_key, en_key in field_mapping.items():
        if cn_key in infobox:
            movie_info[en_key] = infobox[cn_key]
    
    # Also include full infobox
    movie_info["infobox"] = infobox
    
    return movie_info


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Baidu Baike access skill.
    
    Parameters:
        params: Dictionary containing:
            - function (str): The function to call:
                - "search": Search for lemmas
                - "get_lemma": Get lemma details
                - "get_movie_info": Get movie-specific info
            - Additional parameters specific to each function
    
    Returns:
        Dictionary containing function results or error information
    """
    function = params.get("function", "get_lemma")

    # ``ctx`` is a SearchOS SkillContext, NOT a Playwright BrowserContext.
    # This skill drives Playwright itself, so the sub-functions must init their
    # own browser (context=None path). Forwarding ctx made them treat it as a
    # Playwright context and call ctx.new_page() → AttributeError.
    if function == "search":
        return await search(params)
    elif function == "get_lemma":
        return await get_lemma(params)
    elif function == "get_movie_info":
        return await get_movie_info(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Valid functions are: search, get_lemma, get_movie_info"
        }


# For testing
if __name__ == "__main__":
    async def test():
        # Test search
        print("Testing search...")
        result = await search({"keyword": "八佰"})
        print(f"Search result: {result}")
        
        # Test get_lemma with URL
        print("\nTesting get_lemma with URL...")
        result = await get_lemma({"url": "https://baike.baidu.com/item/%E5%85%AB%E4%BD%B0/20785278"})
        print(f"Lemma result: Success={result['success']}, Title={result.get('title')}")
        print(f"Infobox items: {len(result.get('infobox', {}))}")
        
        # Test get_movie_info
        print("\nTesting get_movie_info...")
        result = await get_movie_info({"keyword": "你好，李焕英"})
        print(f"Movie result: Success={result['success']}, Title={result.get('title')}")
        print(f"Director: {result.get('director')}")
        print(f"Box office: {result.get('box_office')}")
        
        # Test 404
        print("\nTesting 404 error...")
        result = await get_lemma({"url": "https://baike.baidu.com/item/%E9%95%BF%E6%B4%A5%E6%B9%96/56287878"})
        print(f"404 result: {result}")
    
    asyncio.run(test())