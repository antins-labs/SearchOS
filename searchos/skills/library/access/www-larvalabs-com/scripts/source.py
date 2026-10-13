"""
SearchOS Access Skill for Larva Labs CryptoPunks Detail Pages
Extracts structured data from CryptoPunk detail pages including attributes,
market status, and transaction history.
"""

import asyncio
import re
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the Larva Labs CryptoPunks access skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ('get_punk_details' or 'get_punk_transactions')
            - punk_id: The CryptoPunk ID (e.g., '5822', '7804')
            - url: Optional full URL (if not provided, constructed from punk_id)
            - transaction_limit: Max transactions to return (default 50, max 500)

    
    Returns:
        Dictionary with structured punk data or error information
    """
    function = params.get("function", "get_punk_details")
    
    # Get punk_id from params or URL
    punk_id = params.get("punk_id")
    url = params.get("url")
    
    if url:
        # Extract punk_id from URL
        match = re.search(r'/details/(\d+)$', url)
        if match:
            punk_id = match.group(1)
        else:
            return {"error": "Invalid URL format. Expected: /cryptopunks/details/{punk_id}"}
    elif punk_id:
        url = f"https://www.larvalabs.com/cryptopunks/details/{punk_id}"
    else:
        return {"error": "Either punk_id or url parameter is required"}
    
    # Validate punk_id
    try:
        punk_id_int = int(punk_id)
        if punk_id_int < 0 or punk_id_int > 9999:
            return {"error": f"Invalid punk_id: {punk_id}. Must be between 0 and 9999"}
    except ValueError:
        return {"error": f"Invalid punk_id: {punk_id}. Must be a numeric value"}
    
    if function == "get_punk_details":
        return await _get_punk_details(url, punk_id)
    elif function == "get_punk_transactions":
        transaction_limit = min(int(params.get("transaction_limit", 50)), 500)
        return await _get_punk_transactions(url, punk_id, transaction_limit)
    else:
        return {"error": f"Unknown function: {function}"}


async def _get_punk_details(url: str, punk_id: str) -> dict[str, Any]:
    """
    Fetch comprehensive punk details including attributes and market status.
    """
    from playwright.async_api import async_playwright
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                # Navigate with timeout
                await page.goto(url, wait_until="load", timeout=60000)
                await asyncio.sleep(2)  # Wait for dynamic content
                
                # Extract basic info
                title = await page.title()
                body_text = await page.locator("body").inner_text()
                
                # Extract punk type/rarity
                type_match = re.search(r'One of (\d+) (\w+) punks', body_text)
                punk_type = type_match.group(2) if type_match else None
                type_count = int(type_match.group(1)) if type_match else None
                
                # Extract attributes
                attributes = []
                try:
                    attr_heading = page.locator("text=Attributes").first
                    parent = attr_heading.locator("xpath=..")
                    attr_divs = parent.locator("div.col-md-4")
                    attr_count = await attr_divs.count()
                    
                    for i in range(attr_count):
                        attr_div = attr_divs.nth(i)
                        text = await attr_div.inner_text()
                        attr_match = re.match(r'(.+?)\n(\d+) punks have this', text.strip())
                        if attr_match:
                            attributes.append({
                                "name": attr_match.group(1).strip(),
                                "count": int(attr_match.group(2))
                            })
                except Exception as e:
                    # Attributes section might not exist for some punks
                    pass
                
                # Extract market status
                market_status = {}
                try:
                    market_heading = page.locator("text=Current Market Status").first
                    market_parent = market_heading.locator("xpath=..")
                    market_text = await market_parent.inner_text()
                    
                    # Parse owner
                    owner_match = re.search(r'owned by address ([^\.\n]+)', market_text)
                    if owner_match:
                        market_status["owner"] = owner_match.group(1).strip()
                    
                    # Parse for sale status
                    market_status["for_sale"] = "listed for sale" in market_text and "has not been listed" not in market_text
                    
                    # Parse current bid
                    bid_match = re.search(r'There is a bid of ([^\s]+Ξ) \([^\)]+\) for this punk from ([^\.\n]+)', market_text)
                    if bid_match:
                        market_status["current_bid"] = {
                            "amount": bid_match.group(1),
                            "from": bid_match.group(2).strip()
                        }
                    else:
                        market_status["current_bid"] = None
                        
                    # Check if there are no bids
                    market_status["has_bids"] = "currently no bids" not in market_text
                    
                except Exception as e:
                    market_status = {"error": str(e)}
                
                # Extract image URL
                image_url = None
                try:
                    img = page.locator("img[src*='punk']").first
                    if await img.count() > 0:
                        img_src = await img.get_attribute("src")
                        if img_src:
                            # Make it absolute URL
                            if img_src.startswith("/"):
                                image_url = f"https://www.larvalabs.com{img_src}"
                            else:
                                image_url = img_src
                except:
                    pass
                
                # Get transaction count
                tx_count = 0
                try:
                    table = page.locator("table").first
                    rows = table.locator("tr")
                    tx_count = await rows.count()
                    tx_count = max(0, tx_count - 1)  # Subtract header row
                except:
                    pass
                
                return {
                    "success": True,
                    "punk_id": punk_id,
                    "url": url,
                    "title": title,
                    "type": punk_type,
                    "type_count": type_count,
                    "attributes": attributes,
                    "attribute_count": len(attributes),
                    "market_status": market_status,
                    "image_url": image_url,
                    "transaction_count": tx_count
                }
                
            finally:
                await browser.close()
                
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Page load timeout",
            "punk_id": punk_id,
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "punk_id": punk_id,
            "url": url
        }


async def _get_punk_transactions(url: str, punk_id: str, limit: int) -> dict[str, Any]:
    """
    Fetch transaction history for a punk.
    """
    from playwright.async_api import async_playwright
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = await context.new_page()
                
                # Navigate with timeout
                await page.goto(url, wait_until="load", timeout=60000)
                await asyncio.sleep(2)  # Wait for dynamic content
                
                # Extract transactions
                transactions = []
                table = page.locator("table").first
                rows = table.locator("tr")
                row_count = await rows.count()
                
                # Limit to requested number
                max_rows = min(row_count, limit + 1)  # +1 for header
                
                for i in range(1, max_rows):  # Skip header row
                    row = rows.nth(i)
                    cells = await row.locator("td").all_inner_texts()
                    
                    if len(cells) >= 5:
                        tx = {
                            "type": cells[0],
                            "from": cells[1] if cells[1] else None,
                            "to": cells[2] if cells[2] else None,
                            "amount": cells[3] if cells[3] else None,
                            "date": cells[4]
                        }
                        transactions.append(tx)
                
                # Get summary statistics
                tx_types = {}
                for tx in transactions:
                    tx_type = tx["type"]
                    tx_types[tx_type] = tx_types.get(tx_type, 0) + 1
                
                # Find last sale
                last_sale = None
                for tx in transactions:
                    if tx["type"] == "Sold":
                        last_sale = tx
                        break
                
                return {
                    "success": True,
                    "punk_id": punk_id,
                    "url": url,
                    "total_transactions": row_count - 1,
                    "returned_transactions": len(transactions),
                    "transactions": transactions,
                    "transaction_type_summary": tx_types,
                    "last_sale": last_sale
                }
                
            finally:
                await browser.close()
                
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Page load timeout",
            "punk_id": punk_id,
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "punk_id": punk_id,
            "url": url
        }