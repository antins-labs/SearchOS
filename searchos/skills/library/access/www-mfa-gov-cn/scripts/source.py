"""
SearchOS Access Skill for Chinese Ministry of Foreign Affairs (MFA) Visa Agreement Data
Extracts structured visa exemption agreement table from www.mfa.gov.cn
"""

import re
from typing import Any
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute function for MFA visa agreement skill.
    
    Parameters:
        params: dict with 'function' key and function-specific parameters

    
    Returns:
        dict with structured results or error information
    """
    function = params.get("function", "")
    
    if function == "get_visa_agreements":
        return await get_visa_agreements(params)
    elif function == "search_by_country":
        return await search_by_country(params)
    elif function == "get_by_passport_type":
        return await get_by_passport_type(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_visa_agreements", "search_by_country", "get_by_passport_type"]
        }


async def fetch_page_data(url: str = None) -> dict:
    """
    Fetch and parse the visa agreement table from MFA website.
    Uses Playwright to handle the complex table structure with rowspan.
    """
    if url is None:
        url = "https://www.mfa.gov.cn/wjbzwfwpt/kzx/tzgg/202504/t20250414_11594222.html"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                locale='zh-CN',
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(2000)
            
            # Extract page metadata
            title = await page.title()
            
            # Get update date from page content
            body_text = await page.locator('body').inner_text()
            update_match = re.search(r'更新至(\d{4}年\d{1,2}月\d{1,2}日)', body_text)
            update_date = update_match.group(1) if update_match else None
            
            # Extract table with proper rowspan handling
            table_data = await page.evaluate('''() => {
                const table = document.querySelector('table');
                if (!table) return null;
                
                const rows = table.querySelectorAll('tr');
                const headers = [];
                const agreements = [];
                
                // First row is header
                const headerCells = rows[0].querySelectorAll('th, td');
                headerCells.forEach(cell => {
                    headers.push(cell.innerText.trim());
                });
                
                // Parse data rows with rowspan tracking
                const rowspanTracker = {}; // Track active rowspans by column
                
                for (let i = 1; i < rows.length; i++) {
                    const cells = rows[i].querySelectorAll('td');
                    const rowData = {};
                    let cellIndex = 0;
                    
                    for (let col = 0; col < headers.length; col++) {
                        // Check if this column has an active rowspan from previous row
                        if (rowspanTracker[col] && rowspanTracker[col].remaining > 0) {
                            rowData[headers[col]] = rowspanTracker[col].value;
                            rowspanTracker[col].remaining--;
                        } else if (cellIndex < cells.length) {
                            // Get actual cell data
                            const cell = cells[cellIndex];
                            const text = cell.innerText.trim();
                            const rowspan = cell.rowSpan || 1;
                            
                            rowData[headers[col]] = text;
                            
                            // Track rowspan if > 1
                            if (rowspan > 1) {
                                rowspanTracker[col] = {
                                    value: text,
                                    remaining: rowspan - 1
                                };
                            }
                            cellIndex++;
                        }
                    }
                    
                    // Only add if we have meaningful data
                    if (rowData['序号'] || rowData['互免签证的证件类别']) {
                        agreements.push(rowData);
                    }
                }
                
                return { headers, agreements };
            }''')
            
            if not table_data:
                return {
                    "success": False,
                    "error": "Failed to parse table data"
                }
            
            # Process and structure the data
            structured_agreements = process_agreements(table_data['agreements'])
            
            return {
                "success": True,
                "page_title": title,
                "update_date": update_date,
                "source_url": url,
                "headers": table_data['headers'],
                "total_countries": len(structured_agreements),
                "agreements": structured_agreements
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch page: {str(e)}"
            }
        finally:
            await browser.close()


def process_agreements(raw_agreements: list) -> list:
    """
    Process raw table data into structured country agreement records.
    Handles the rowspan grouping where one country may have multiple passport types.
    Groups all agreements by country sequence number.
    """
    # Group rows by sequence number
    country_groups = {}
    
    for row in raw_agreements:
        seq_num = row.get('序号', '').strip()
        
        # Extract agreement data
        passport_type = row.get('互免签证的证件类别', '').strip()
        effective_date = row.get('生效日期', '').strip()
        remarks = row.get('备注', '').strip()
        country_name = row.get('协议国', '').strip()
        
        if not passport_type:
            continue
        
        # If has sequence number, use it as key
        if seq_num and seq_num.isdigit():
            seq_key = int(seq_num)
            
            if seq_key not in country_groups:
                country_groups[seq_key] = {
                    "序号": seq_key,
                    "协议国": country_name,
                    "互免签证协定": []
                }
            
            country_groups[seq_key]["互免签证协定"].append({
                "证件类别": passport_type,
                "生效日期": effective_date,
                "备注": remarks
            })
    
    # Convert to list and sort by sequence number
    structured = [country_groups[key] for key in sorted(country_groups.keys())]
    
    return structured


async def get_visa_agreements(params: dict) -> dict:
    """
    Fetch the complete visa agreements table.
    
    Parameters:
        url (optional): Specific URL to fetch from
    
    Returns:
        Complete structured visa agreement data
    """
    url = params.get("url")
    
    result = await fetch_page_data(url)
    
    if result["success"]:
        # Add summary statistics
        agreements = result["agreements"]
        
        # Count passport types
        passport_counts = {}
        for country in agreements:
            for agr in country["互免签证协定"]:
                pt = agr["证件类别"]
                if "普通护照" in pt:
                    passport_counts["普通护照"] = passport_counts.get("普通护照", 0) + 1
                if "公务普通" in pt:
                    passport_counts["公务普通护照"] = passport_counts.get("公务普通护照", 0) + 1
                if "公务护照" in pt and "公务普通" not in pt:
                    passport_counts["公务护照"] = passport_counts.get("公务护照", 0) + 1
                if "外交护照" in pt:
                    passport_counts["外交护照"] = passport_counts.get("外交护照", 0) + 1
        
        result["statistics"] = {
            "total_countries": len(agreements),
            "passport_type_coverage": passport_counts
        }
    
    return result


async def search_by_country(params: dict) -> dict:
    """
    Search for visa agreement information by country name.
    
    Parameters:
        country: Country name to search for (Chinese or partial match)
        url (optional): Specific URL to fetch from
    
    Returns:
        Matching country visa agreement data
    """
    country = params.get("country", "").strip()
    
    if not country:
        return {
            "success": False,
            "error": "Parameter 'country' is required"
        }
    
    result = await fetch_page_data(params.get("url"))
    
    if not result["success"]:
        return result
    
    # Search for matching countries (exact match first, then partial)
    exact_match = None
    partial_matches = []
    
    for agr in result["agreements"]:
        if agr["协议国"] == country:
            exact_match = agr
            break
        elif country in agr["协议国"]:
            partial_matches.append(agr)
    
    if exact_match:
        return {
            "success": True,
            "query": country,
            "found": True,
            "match_type": "exact",
            "matches": [exact_match],
            "match_count": 1,
            "update_date": result["update_date"],
            "source_url": result["source_url"]
        }
    
    if partial_matches:
        return {
            "success": True,
            "query": country,
            "found": True,
            "match_type": "partial",
            "matches": partial_matches,
            "match_count": len(partial_matches),
            "update_date": result["update_date"],
            "source_url": result["source_url"]
        }
    
    return {
        "success": True,
        "query": country,
        "found": False,
        "message": f"No country matching '{country}' found",
        "total_countries": result["total_countries"],
        "update_date": result["update_date"]
    }


async def get_by_passport_type(params: dict) -> dict:
    """
    Get countries that have visa exemption for a specific passport type.
    
    Parameters:
        passport_type: Type of passport (e.g., "普通护照", "外交护照", "公务护照")
        url (optional): Specific URL to fetch from
    
    Returns:
        List of countries with visa exemption for the specified passport type
    """
    passport_type = params.get("passport_type", "").strip()
    
    if not passport_type:
        return {
            "success": False,
            "error": "Parameter 'passport_type' is required"
        }
    
    result = await fetch_page_data(params.get("url"))
    
    if not result["success"]:
        return result
    
    # Normalize passport type for matching
    passport_keywords = {
        "普通": "普通护照",
        "普通护照": "普通护照",
        "ordinary": "普通护照",
        "外交": "外交护照",
        "外交护照": "外交护照",
        "diplomatic": "外交护照",
        "公务": "公务护照",
        "公务护照": "公务护照",
        "公务普通": "公务普通护照",
        "公务普通护照": "公务普通护照",
        "official": "公务护照",
        "service": "公务护照"
    }
    
    search_term = passport_keywords.get(passport_type, passport_type)
    
    # Find countries with matching passport type
    matches = []
    seen_countries = set()
    
    for country in result["agreements"]:
        if country["协议国"] in seen_countries:
            continue
            
        for agr in country["互免签证协定"]:
            if search_term in agr["证件类别"]:
                matches.append({
                    "序号": country["序号"],
                    "协议国": country["协议国"],
                    "证件类别": agr["证件类别"],
                    "生效日期": agr["生效日期"],
                    "备注": agr["备注"]
                })
                seen_countries.add(country["协议国"])
                break  # Only add country once
    
    return {
        "success": True,
        "passport_type": passport_type,
        "search_term": search_term,
        "found": len(matches) > 0,
        "countries": matches,
        "country_count": len(matches),
        "update_date": result["update_date"],
        "source_url": result["source_url"]
    }