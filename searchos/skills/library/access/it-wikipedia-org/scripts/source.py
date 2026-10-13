"""
SearchOS access skill for Italian Wikipedia (it.wikipedia.org).

Extracts structured data including:
- Page metadata and categories
- Infobox data via Wikidata
- Bibliography entries
- Section list
- Full text content
"""

import httpx
import re
from typing import Any, Optional
from bs4 import BeautifulSoup


BASE_URL = "https://it.wikipedia.org/w/api.php"
WIKIDATA_URL = "https://www.wikidata.org/wiki/Special:EntityData"
HEADERS = {
    "User-Agent": "SearchOS-Wikipedia-Skill/1.0 (https://github.com/searchos/wikipedia-skill; contact@example.com)"
}

# Wikidata property mappings
WD_PROPERTIES = {
    "P31": "instance_of",
    "P106": "occupation",
    "P569": "birth_date",
    "P570": "death_date",
    "P19": "birth_place",
    "P20": "death_place",
    "P166": "awards",
    "P27": "country",
    "P1412": "language",
    "P103": "native_language",
    "P21": "gender",
    "P26": "spouse",
    "P22": "father",
    "P25": "mother",
    "P40": "children",
    "P69": "educated_at",
    "P106": "occupation",
    "P345": "imdb_id",
    "P18": "image",
}


async def execute(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """Main entry point for the Wikipedia skill."""
    
    function = params.get("function")
    
    if function == "get_page":
        return await get_page(params, ctx)
    elif function == "get_sections":
        return await get_sections(params, ctx)
    elif function == "get_bibliography":
        return await get_bibliography(params, ctx)
    elif function == "get_infobox":
        return await get_infobox(params, ctx)
    elif function == "get_wikidata":
        return await get_wikidata(params, ctx)
    elif function == "search":
        return await search_pages(params, ctx)
    else:
        return {"error": f"Unknown function: {function}"}


async def _make_request(params: dict) -> dict:
    """Make a request to the Wikipedia API."""
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        response = await client.get(BASE_URL, params=params)
        response.raise_for_status()
        return response.json()


async def _make_wikidata_request(entity_id: str) -> dict:
    """Make a request to the Wikidata API."""
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        url = f"{WIKIDATA_URL}/{entity_id}.json"
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def get_page(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """
    Get comprehensive page information including metadata, categories, and summary.
    
    Parameters:
        - title: Wikipedia page title
    """
    title = params.get("title", "").strip()
    if not title:
        return {"error": "Missing required parameter: title"}
    
    try:
        # Get page metadata
        query_params = {
            "action": "query",
            "titles": title,
            "prop": "info|categories|pageprops|extracts",
            "exintro": "true",
            "explaintext": "true",
            "exsentences": "5",
            "ppprop": "wikibase_item",
            "cllimit": "50",
            "format": "json",
            "formatversion": "2"
        }
        
        data = await _make_request(query_params)
        
        if "query" not in data or not data["query"]["pages"]:
            return {"error": f"Page not found: {title}"}
        
        page = data["query"]["pages"][0]
        
        if "missing" in page:
            return {"error": f"Page not found: {title}"}
        
        result = {
            "title": page.get("title"),
            "page_id": page.get("pageid"),
            "last_modified": page.get("touched"),
            "url": f"https://it.wikipedia.org/wiki/{title.replace(' ', '_')}",
            "summary": page.get("extract", ""),
            "categories": [],
            "wikidata_id": None
        }
        
        if "pageprops" in page:
            result["wikidata_id"] = page["pageprops"].get("wikibase_item")
        
        if "categories" in page:
            result["categories"] = [cat.get("title", "").replace("Categoria:", "") 
                                   for cat in page["categories"]]
        
        return result
        
    except Exception as e:
        return {"error": f"Failed to fetch page: {str(e)}"}


async def get_sections(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """
    Get list of sections in a Wikipedia page.
    
    Parameters:
        - title: Wikipedia page title
    """
    title = params.get("title", "").strip()
    if not title:
        return {"error": "Missing required parameter: title"}
    
    try:
        parse_params = {
            "action": "parse",
            "page": title,
            "prop": "sections",
            "format": "json",
            "formatversion": "2"
        }
        
        data = await _make_request(parse_params)
        
        if "parse" not in data:
            if "error" in data:
                return {"error": data["error"].get("info", "Unknown error")}
            return {"error": "Failed to parse page"}
        
        sections = data["parse"].get("sections", [])
        
        result = {
            "title": data["parse"].get("title", title),
            "sections": [
                {
                    "index": sec.get("index"),
                    "title": sec.get("line", ""),
                    "anchor": sec.get("anchor", ""),
                    "level": sec.get("level", "2"),
                    "toc_level": sec.get("toclevel", 1)
                }
                for sec in sections
            ]
        }
        
        return result
        
    except Exception as e:
        return {"error": f"Failed to fetch sections: {str(e)}"}


async def get_bibliography(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """
    Extract bibliography entries from a Wikipedia page.
    
    Parameters:
        - title: Wikipedia page title
        - limit: Maximum number of entries to return (default: 50)
    """
    title = params.get("title", "").strip()
    if not title:
        return {"error": "Missing required parameter: title"}
    
    limit = params.get("limit", 50)
    
    try:
        # First, get sections to find bibliography index
        sections_params = {
            "action": "parse",
            "page": title,
            "prop": "sections",
            "format": "json",
            "formatversion": "2"
        }
        
        sections_data = await _make_request(sections_params)
        
        if "parse" not in sections_data:
            return {"error": "Failed to get page sections"}
        
        # Find bibliography section
        sections = sections_data["parse"].get("sections", [])
        biblio_index = None
        biblio_title = None
        
        for sec in sections:
            sec_title = sec.get("line", "").lower()
            sec_anchor = sec.get("anchor", "").lower()
            if "bibliograf" in sec_title or "bibliograf" in sec_anchor:
                biblio_index = sec.get("index")
                biblio_title = sec.get("line", "Bibliografia")
                break
        
        if not biblio_index:
            return {
                "title": title,
                "bibliography": [],
                "count": 0,
                "error": "No bibliography section found"
            }
        
        # Get the HTML content of bibliography section
        text_params = {
            "action": "parse",
            "page": title,
            "prop": "text",
            "section": biblio_index,
            "format": "json",
            "formatversion": "2"
        }
        
        text_data = await _make_request(text_params)
        
        if "parse" not in text_data:
            return {"error": "Failed to get bibliography content"}
        
        html = text_data["parse"].get("text", "")
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract bibliography entries
        items = soup.find_all("li")
        bibliography = []
        
        for item in items[:limit]:
            text = item.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            
            # Extract links
            links = item.find_all("a")
            link_titles = [a.get("title", a.get_text(strip=True)) 
                          for a in links if a.get("title")]
            
            # Parse citation info (basic parsing)
            entry = {
                "text": text,
                "links": link_titles[:5]  # Limit links
            }
            
            # Try to extract common citation patterns
            # Author, Title, Publisher, Year pattern
            author_match = re.match(r'^([^,]+),\s*(.+)', text)
            if author_match:
                entry["author"] = author_match.group(1).strip()
                entry["rest"] = author_match.group(2).strip()
            
            bibliography.append(entry)
        
        return {
            "title": title,
            "section": biblio_title,
            "bibliography": bibliography,
            "count": len(bibliography)
        }
        
    except Exception as e:
        return {"error": f"Failed to fetch bibliography: {str(e)}"}


async def get_infobox(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """
    Extract infobox/structured data from a Wikipedia page via Wikidata.
    
    Parameters:
        - title: Wikipedia page title
    """
    title = params.get("title", "").strip()
    if not title:
        return {"error": "Missing required parameter: title"}
    
    try:
        # First get the Wikidata ID
        query_params = {
            "action": "query",
            "titles": title,
            "prop": "pageprops",
            "ppprop": "wikibase_item",
            "format": "json",
            "formatversion": "2"
        }
        
        query_data = await _make_request(query_params)
        
        if "query" not in query_data or not query_data["query"]["pages"]:
            return {"error": f"Page not found: {title}"}
        
        page = query_data["query"]["pages"][0]
        
        if "missing" in page:
            return {"error": f"Page not found: {title}"}
        
        wikidata_id = page.get("pageprops", {}).get("wikibase_item")
        
        if not wikidata_id:
            return {
                "title": title,
                "infobox": {},
                "error": "No Wikidata item found for this page"
            }
        
        # Get Wikidata
        wikidata = await _make_wikidata_request(wikidata_id)
        
        if wikidata_id not in wikidata.get("entities", {}):
            return {"error": "Failed to fetch Wikidata"}
        
        entity = wikidata["entities"][wikidata_id]
        
        # Extract labels and descriptions
        labels = entity.get("labels", {})
        descriptions = entity.get("descriptions", {})
        
        result = {
            "title": title,
            "wikidata_id": wikidata_id,
            "label": labels.get("it", labels.get("en", {})).get("value", title),
            "description": descriptions.get("it", descriptions.get("en", {})).get("value", ""),
            "infobox": {}
        }
        
        # Extract properties
        claims = entity.get("claims", {})
        
        # Helper to get label from Wikidata item
        async def get_item_label(item_id: str) -> str:
            try:
                item_data = await _make_wikidata_request(item_id)
                if item_id in item_data.get("entities", {}):
                    item_entity = item_data["entities"][item_id]
                    labels = item_entity.get("labels", {})
                    return labels.get("it", labels.get("en", {})).get("value", item_id)
            except:
                pass
            return item_id
        
        # Extract common properties
        for prop_id, prop_name in WD_PROPERTIES.items():
            if prop_id in claims:
                values = []
                for claim in claims[prop_id]:
                    try:
                        mainsnak = claim["mainsnak"]
                        datatype = mainsnak.get("datatype")
                        datavalue = mainsnak.get("datavalue", {})
                        
                        if datatype == "wikibase-item":
                            item_id = datavalue["value"]["id"]
                            # For performance, limit item label lookups
                            if len(values) < 3:
                                label = await get_item_label(item_id)
                                values.append(label)
                            else:
                                values.append(item_id)
                        
                        elif datatype == "time":
                            time_val = datavalue["value"]["time"]
                            precision = datavalue["value"]["precision"]
                            # Format based on precision
                            if precision >= 11:  # Day precision
                                date_str = time_val[1:11]  # +YYYY-MM-DD
                            elif precision >= 10:  # Month precision
                                date_str = time_val[1:7]  # +YYYY-MM
                            else:  # Year precision
                                date_str = time_val[1:5]  # +YYYY
                            values.append(date_str)
                        
                        elif datatype == "string":
                            values.append(datavalue.get("value", ""))
                        
                        elif datatype == "url":
                            values.append(datavalue.get("value", ""))
                        
                        elif datatype == "monolingualtext":
                            text = datavalue.get("value", {})
                            values.append(text.get("text", ""))
                    
                    except Exception:
                        continue
                
                if values:
                    result["infobox"][prop_name] = values if len(values) > 1 else values[0]
        
        return result
        
    except Exception as e:
        return {"error": f"Failed to fetch infobox: {str(e)}"}


async def get_wikidata(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """
    Get raw Wikidata for a Wikipedia page.
    
    Parameters:
        - title: Wikipedia page title (optional if wikidata_id provided)
        - wikidata_id: Wikidata entity ID (optional if title provided)
    """
    title = params.get("title", "").strip()
    wikidata_id = params.get("wikidata_id", "").strip()
    
    if not wikidata_id and not title:
        return {"error": "Missing required parameter: title or wikidata_id"}
    
    try:
        if not wikidata_id:
            # Get Wikidata ID from Wikipedia
            query_params = {
                "action": "query",
                "titles": title,
                "prop": "pageprops",
                "ppprop": "wikibase_item",
                "format": "json",
                "formatversion": "2"
            }
            
            query_data = await _make_request(query_params)
            
            if "query" not in query_data or not query_data["query"]["pages"]:
                return {"error": f"Page not found: {title}"}
            
            page = query_data["query"]["pages"][0]
            
            if "missing" in page:
                return {"error": f"Page not found: {title}"}
            
            wikidata_id = page.get("pageprops", {}).get("wikibase_item")
            
            if not wikidata_id:
                return {"error": "No Wikidata item found for this page"}
        
        # Get Wikidata
        wikidata = await _make_wikidata_request(wikidata_id)
        
        if wikidata_id not in wikidata.get("entities", {}):
            return {"error": "Failed to fetch Wikidata"}
        
        entity = wikidata["entities"][wikidata_id]
        
        # Return simplified Wikidata
        result = {
            "wikidata_id": wikidata_id,
            "labels": entity.get("labels", {}),
            "descriptions": entity.get("descriptions", {}),
            "aliases": entity.get("aliases", {}),
            "claims": entity.get("claims", {}),
            "sitelinks": entity.get("sitelinks", {})
        }
        
        return result
        
    except Exception as e:
        return {"error": f"Failed to fetch Wikidata: {str(e)}"}


async def search_pages(params: dict[str, Any], ctx: Any) -> dict[str, Any]:
    """
    Search for Wikipedia pages.
    
    Parameters:
        - query: Search query
        - limit: Maximum number of results (default: 10)
    """
    query = params.get("query", "").strip()
    if not query:
        return {"error": "Missing required parameter: query"}
    
    limit = params.get("limit", 10)
    
    try:
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
            "srprop": "size|wordcount|timestamp|snippet",
            "format": "json",
            "formatversion": "2"
        }
        
        data = await _make_request(search_params)
        
        if "query" not in data or "search" not in data["query"]:
            return {"error": "Search failed"}
        
        results = []
        for item in data["query"]["search"]:
            results.append({
                "title": item.get("title"),
                "page_id": item.get("pageid"),
                "word_count": item.get("wordcount"),
                "size": item.get("size"),
                "snippet": item.get("snippet", "").replace('<span class="searchmatch">', '').replace('</span>', ''),
                "timestamp": item.get("timestamp"),
                "url": f"https://it.wikipedia.org/wiki/{item.get('title', '').replace(' ', '_')}"
            })
        
        return {
            "query": query,
            "count": len(results),
            "results": results
        }
        
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}