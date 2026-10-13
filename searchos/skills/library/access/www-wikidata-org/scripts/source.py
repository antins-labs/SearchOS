"""
Wikidata Access Skill for SearchOS

This skill provides structured access to Wikidata items, including:
- Fetching Wikidata items by ID
- Searching for Wikidata entities
- Extracting claims (properties), sitelinks, and labels
"""

from typing import Any
from playwright.async_api import async_playwright


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Wikidata access functions.
    
    Args:
        params: Dictionary containing:
            - function: The function to call (get_item, search_items)
            - item_id: Wikidata item ID (e.g., Q926972) for get_item
            - query: Search query for search_items
            - language: Language code for labels (default: "en")
            - properties: List of specific property IDs to fetch (optional)
            - include_sitelinks: Whether to include sitelinks (default: true)

    
    Returns:
        Dictionary with structured Wikidata data or error information
    """
    function = params.get("function")
    
    if function == "get_item":
        return await get_item(params)
    elif function == "search_items":
        return await search_items(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_item", "search_items"]
        }


async def get_item(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch a Wikidata item by its ID.
    
    Args:
        params: Dictionary containing:
            - item_id: Wikidata item ID (e.g., Q926972)
            - language: Language code for labels (default: "en")
            - properties: List of specific property IDs to fetch (optional)
            - include_sitelinks: Whether to include sitelinks (default: true)
    
    Returns:
        Dictionary with item data including:
            - id: Wikidata item ID
            - label: Item label
            - description: Item description
            - aliases: List of aliases
            - claims: Dictionary of property claims
            - sitelinks: Dictionary of sitelinks (if requested)
    """
    item_id = params.get("item_id")
    if not item_id:
        return {
            "success": False,
            "error": "item_id is required"
        }
    
    # Normalize item ID
    item_id = item_id.upper().strip()
    if not item_id.startswith("Q"):
        item_id = f"Q{item_id}"
    
    language = params.get("language", "en")
    properties_filter = params.get("properties")  # Optional list of property IDs
    include_sitelinks = params.get("include_sitelinks", True)
    
    url = f"https://www.wikidata.org/wiki/{item_id}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale=language
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Check if item exists
            if await page.locator(".wikibase-entitytermsview").count() == 0:
                return {
                    "success": False,
                    "error": f"Wikidata item {item_id} not found",
                    "item_id": item_id
                }
            
            # Extract basic info
            label = await page.locator(".wikibase-title-label").first.text_content() if await page.locator(".wikibase-title-label").count() > 0 else None
            description = await page.locator(".wikibase-entitytermsview-description-text").first.text_content() if await page.locator(".wikibase-entitytermsview-description-text").count() > 0 else None
            
            # Extract aliases
            aliases = []
            alias_elements = await page.locator(".wikibase-entitytermsview-aliases li").all()
            for alias_elem in alias_elements:
                alias_text = await alias_elem.text_content()
                if alias_text:
                    aliases.append(alias_text.strip())
            
            # Extract claims (properties)
            claims = {}
            claim_groups = await page.locator(".wikibase-statementgroupview").all()
            
            for group in claim_groups:
                # Get property ID
                prop_link = await group.locator(".wikibase-statementgroupview-property-label a").get_attribute("href") if await group.locator(".wikibase-statementgroupview-property-label a").count() > 0 else None
                prop_id = prop_link.split("/")[-1] if prop_link else None
                
                # Get property label
                prop_label = await group.locator(".wikibase-statementgroupview-property-label").text_content() if await group.locator(".wikibase-statementgroupview-property-label").count() > 0 else None
                prop_label = prop_label.strip() if prop_label else None
                
                # Skip if properties filter is set and this property is not in the list
                if properties_filter and prop_id:
                    if prop_id not in properties_filter and prop_id.replace("Property:", "") not in properties_filter:
                        continue
                
                # Get values
                values = []
                main_snaks = await group.locator(".wikibase-statementview-mainsnak .wikibase-snakview-value").all()
                for snak in main_snaks[:10]:  # Limit to 10 values per property
                    value_text = await snak.text_content()
                    if value_text:
                        # Clean up the value
                        value_text = value_text.strip()
                        # Check if it's a link to another entity - use first() to avoid strict mode
                        link_count = await snak.locator("a").count()
                        linked_id = None
                        if link_count > 0:
                            try:
                                # Get the first link that looks like an entity link
                                links = await snak.locator("a").all()
                                for link in links:
                                    href = await link.get_attribute("href")
                                    if href and href.startswith("/wiki/Q"):
                                        linked_id = href.split("/")[-1]
                                        break
                            except:
                                pass
                        
                        values.append({
                            "text": value_text,
                            "entity_id": linked_id
                        })
                
                if prop_id or prop_label:
                    claims[prop_id or prop_label] = {
                        "property_id": prop_id,
                        "property_label": prop_label,
                        "values": values
                    }
            
            # Extract sitelinks
            sitelinks = {}
            if include_sitelinks:
                sitelink_items = await page.locator(".wikibase-sitelinkview").all()
                for item in sitelink_items:
                    site_id = await item.locator(".wikibase-sitelinkview-siteid-container").text_content() if await item.locator(".wikibase-sitelinkview-siteid-container").count() > 0 else None
                    link_title = await item.locator(".wikibase-sitelinkview-link a").text_content() if await item.locator(".wikibase-sitelinkview-link a").count() > 0 else None
                    link_url = await item.locator(".wikibase-sitelinkview-link a").get_attribute("href") if await item.locator(".wikibase-sitelinkview-link a").count() > 0 else None
                    
                    if site_id:
                        site_id = site_id.strip()
                        sitelinks[site_id] = {
                            "site": site_id,
                            "title": link_title,
                            "url": link_url
                        }
            
            return {
                "success": True,
                "item": {
                    "id": item_id,
                    "label": label.strip() if label else None,
                    "description": description.strip() if description else None,
                    "aliases": aliases,
                    "claims": claims,
                    "sitelinks": sitelinks if include_sitelinks else None,
                    "claims_count": len(claims),
                    "sitelinks_count": len(sitelinks) if include_sitelinks else 0
                },
                "url": url
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch item: {str(e)}",
                "item_id": item_id
            }
        finally:
            await browser.close()


async def search_items(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for Wikidata items.
    
    Args:
        params: Dictionary containing:
            - query: Search query
            - limit: Maximum number of results (default: 20)
    
    Returns:
        Dictionary with search results including:
            - results: List of matching items with id, label, description
            - total: Total number of results returned
    """
    query = params.get("query")
    if not query:
        return {
            "success": False,
            "error": "query is required"
        }
    
    limit = params.get("limit", 20)
    
    # Build search URL
    import urllib.parse
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.wikidata.org/w/index.php?search={encoded_query}&title=Special%3ASearch"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Extract search results
            results = []
            result_items = await page.locator(".mw-search-result").all()
            
            for item in result_items[:limit]:
                # Get heading link
                heading_link = item.locator(".mw-search-result-heading a")
                if await heading_link.count() > 0:
                    title_text = await heading_link.text_content()
                    href = await heading_link.get_attribute("href")
                    
                    # Extract item ID from title (format: "Label (Q123)")
                    item_id = None
                    label = title_text
                    if title_text and "(Q" in title_text:
                        import re
                        match = re.search(r'\(Q(\d+)\)', title_text)
                        if match:
                            item_id = f"Q{match.group(1)}"
                            label = title_text.split(f"({item_id})")[0].strip()
                    
                    # Get description from result
                    desc_elem = item.locator(".mw-search-result-data")
                    description = await desc_elem.text_content() if await desc_elem.count() > 0 else None
                    
                    results.append({
                        "id": item_id,
                        "label": label,
                        "description": description.strip() if description else None,
                        "url": f"https://www.wikidata.org{href}" if href and href.startswith("/") else href
                    })
            
            return {
                "success": True,
                "results": results,
                "total": len(results),
                "query": query,
                "search_url": search_url
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Search failed: {str(e)}",
                "query": query
            }
        finally:
            await browser.close()