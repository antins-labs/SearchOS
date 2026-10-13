"""
EV Specifications Access Skill
Extracts detailed electric vehicle specifications from evspecifications.com
"""

import asyncio
from typing import Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def _extract_specifications(page) -> dict:
    """Extract all specifications from the model page."""
    result = {
        "title": await page.title(),
        "specifications": {}
    }
    
    # Extract year/brand/model from title if possible
    title = result["title"]
    if " - " in title:
        parts = title.split(" - ")
        if len(parts) >= 1:
            result["model_title"] = parts[0].strip()
    
    tables = await page.locator('table').all()
    
    current_section = "General"
    all_specs = {}
    spec_count = {}  # Track count of each key to handle duplicates
    
    for table in tables:
        # Try to get section header from previous sibling
        try:
            prev_text = await table.evaluate('el => el.previousElementSibling?.textContent || ""')
            if prev_text and len(prev_text.strip()) < 150 and prev_text.strip():
                current_section = prev_text.strip()
        except:
            pass
        
        rows = await table.locator('tr').all()
        for row in rows:
            tds = await row.locator('td').all()
            ths = await row.locator('th').all()
            
            # Check for header row (th cells only)
            if ths and len(tds) == 0:
                headers = []
                for th in ths:
                    h = await th.text_content()
                    if h:
                        headers.append(h.strip())
                if headers and len(' '.join(headers)) < 150:
                    current_section = ' '.join(headers)
                continue
            
            # Data row with at least 2 cells
            if len(tds) >= 2:
                key = await tds[0].inner_text()
                val = await tds[1].inner_text()
                
                # Clean key - extract only the main label (first line)
                key = key.split('\n')[0].strip()
                
                # Clean value
                val = ' '.join(val.strip().split())
                
                if key and val and len(key) < 100:
                    # Handle duplicate keys by appending section info if needed
                    if key in all_specs:
                        # If same key appears in different sections, differentiate
                        if all_specs[key]["section"] != current_section:
                            # Keep the first occurrence (usually more important)
                            # but track that there are duplicates
                            spec_count[key] = spec_count.get(key, 1) + 1
                        # Skip duplicate
                        continue
                    
                    all_specs[key] = {
                        "value": val,
                        "section": current_section
                    }
                    spec_count[key] = 1
    
    result["specifications"] = all_specs
    return result


def _organize_specs(specs: dict) -> dict:
    """Organize specifications into categories."""
    organized = {}
    
    for key, data in specs.items():
        section = data.get("section", "General")
        # Clean up section name
        section = section.split('\n')[0].strip()
        if len(section) > 60:
            section = section[:60] + "..."
        
        if section not in organized:
            organized[section] = {}
        organized[section][key] = data["value"]
    
    return organized


def _extract_key_specs(specs: dict, model_title: str = None) -> dict:
    """Extract key specifications for quick access."""
    key_spec_names = [
        "Brand", "Model", "Model year", "Trim", "Market", "Body style",
        "Battery capacity", "Top speed", "Acceleration from 0 to 60 mph",
        "Acceleration from 0 to 100 km/h", "Total system power", "Power",
        "Driving range", "Curb weight", "Number of seats", "Number of doors",
        "Length", "Width", "Height", "Wheelbase", "Trunk volume",
        "Energy efficiency", "Charging time"
    ]
    
    key_specs = {}
    
    # First add Model from model_title if available
    if model_title:
        # Extract model name from title like "2025 Tesla Model X"
        parts = model_title.split()
        if len(parts) >= 2:
            # Try to find brand in specs and use remaining as model
            brand = specs.get("Brand", {}).get("value", "")
            if brand:
                key_specs["Brand"] = brand
                # Find model name after brand in title
                brand_idx = model_title.find(brand)
                if brand_idx >= 0:
                    model_part = model_title[brand_idx + len(brand):].strip()
                    # Remove year prefix
                    year_prefix = specs.get("Model year", {}).get("value", "")
                    if year_prefix:
                        year_part = year_prefix.split()[0]  # Get just the year number
                        model_part = model_part.replace(year_part, "").strip()
                    if model_part:
                        key_specs["Model"] = model_part
    
    for spec_name in key_spec_names:
        if spec_name in specs and spec_name not in key_specs:
            key_specs[spec_name] = specs[spec_name]["value"]
    
    # Try to find range info
    for key, data in specs.items():
        if "range" in key.lower() and "mi" in data["value"].lower():
            if "Range" not in key_specs:
                key_specs["Range"] = data["value"]
            break
    
    return key_specs


def _find_section_by_keyword(specs: dict, keyword: str) -> dict:
    """Find all specifications in sections matching a keyword."""
    results = {}
    keyword_lower = keyword.lower()
    
    for key, data in specs.items():
        section = data.get("section", "").lower()
        if keyword_lower in section or keyword_lower in key.lower():
            results[key] = data["value"]
    
    return results


async def _get_model_specifications(url: str) -> dict:
    """Fetch and extract specifications from a model page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Navigate with timeout
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)
            
            # Extract all specifications
            data = await _extract_specifications(page)
            
            model_title = data.get("model_title")
            
            return {
                "success": True,
                "url": url,
                "title": data.get("title"),
                "model_title": model_title,
                "key_specifications": _extract_key_specs(data["specifications"], model_title),
                "all_specifications": {k: v["value"] for k, v in data["specifications"].items()},
                "organized_specifications": _organize_specs(data["specifications"])
            }
            
        except PlaywrightTimeoutError:
            return {
                "success": False,
                "error": "Page load timeout",
                "url": url
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "url": url
            }
        finally:
            await browser.close()


async def _get_section_data(url: str, section_keyword: str) -> dict:
    """Extract specifications from a specific section."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)
            
            data = await _extract_specifications(page)
            section_data = _find_section_by_keyword(data["specifications"], section_keyword)
            
            return {
                "success": True,
                "url": url,
                "section_keyword": section_keyword,
                "specifications": section_data
            }
            
        except PlaywrightTimeoutError:
            return {
                "success": False,
                "error": "Page load timeout",
                "url": url
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "url": url
            }
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute EV specifications lookup.
    
    Functions:
    - get_model: Get all specifications for a model by URL
    - get_section: Get specifications from a specific section (battery, motor, performance, etc.)
    - get_key_specs: Get key specifications only (brand, model, battery, range, power, etc.)
    """
    function = params.get("function", "")
    
    if function == "get_model":
        url = params.get("url", "")
        if not url:
            return {"success": False, "error": "URL parameter required"}
        
        if "evspecifications.com" not in url:
            return {"success": False, "error": "URL must be from evspecifications.com"}
        
        return await _get_model_specifications(url)
    
    elif function == "get_section":
        url = params.get("url", "")
        section = params.get("section", "")
        
        if not url:
            return {"success": False, "error": "URL parameter required"}
        if not section:
            return {"success": False, "error": "section parameter required"}
        
        if "evspecifications.com" not in url:
            return {"success": False, "error": "URL must be from evspecifications.com"}
        
        return await _get_section_data(url, section)
    
    elif function == "get_key_specs":
        url = params.get("url", "")
        if not url:
            return {"success": False, "error": "URL parameter required"}
        
        if "evspecifications.com" not in url:
            return {"success": False, "error": "URL must be from evspecifications.com"}
        
        full_data = await _get_model_specifications(url)
        if not full_data.get("success"):
            return full_data
        
        return {
            "success": True,
            "url": url,
            "title": full_data.get("title"),
            "model_title": full_data.get("model_title"),
            "key_specifications": full_data.get("key_specifications", {})
        }
    
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. Available functions: get_model, get_section, get_key_specs"
        }