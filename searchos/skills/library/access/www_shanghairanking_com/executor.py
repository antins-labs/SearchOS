"""
ShanghaiRanking's Global Ranking of Academic Subjects (GRAS) Access Skill

This skill extracts university rankings from ShanghaiRanking's GRAS database.
The site uses Nuxt.js with static payload files containing JSONP-formatted data.

API Structure:
- Main page provides build hash in HTML: /_nuxt/static/{build_hash}/
- Subject rankings payload: /_nuxt/static/{build_hash}/rankings/gras/{year}/{subject_code}/payload.js
- Main GRAS page payload: /_nuxt/static/{build_hash}/rankings/gras/{year}/payload.js
- Payload format: __NUXT_JSONP__("/path", {...data...});

The payload.js files contain obfuscated JSONP that we parse using Node.js.
"""

import asyncio
import json
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

import httpx

BASE_URL = "https://www.shanghairanking.com"
CACHE_TTL = 3600  # 1 hour cache for build hash

# Global cache for build hash
_build_hash_cache: Optional[str] = None


async def get_build_hash(client: httpx.AsyncClient) -> str:
    """Get the current Nuxt build hash from the main page."""
    global _build_hash_cache
    
    if _build_hash_cache:
        return _build_hash_cache
    
    resp = await client.get(f"{BASE_URL}/rankings/gras/2024")
    resp.raise_for_status()
    
    match = re.search(r'_nuxt/static/(\d+)/', resp.text)
    if not match:
        raise ValueError("Could not find build hash in page")
    
    _build_hash_cache = match.group(1)
    return _build_hash_cache


def parse_nuxt_payload(content: str) -> Dict[str, Any]:
    """Parse NUXT JSONP payload using Node.js."""
    # Convert JSONP to a simple variable assignment
    js_code = content.replace("__NUXT_JSONP__", "var result = ") + "\nconsole.log(JSON.stringify(result));"
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
        f.write(js_code)
        temp_path = f.name
    
    try:
        result = subprocess.run(
            ['node', temp_path],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            raise ValueError(f"Node.js parsing failed: {result.stderr}")
        
        return json.loads(result.stdout)
    finally:
        os.unlink(temp_path)


def process_ranking_data(uni: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single university ranking entry."""
    return {
        "rank": uni.get("ranking", ""),
        "university": {
            "name": uni.get("univNameEn", ""),
            "slug": uni.get("univUp", ""),
            "code": uni.get("univCode", ""),
            "logo": f"{BASE_URL}/{uni.get('univLogo', '')}" if uni.get("univLogo") else None,
        },
        "country": uni.get("region", ""),
        "country_code": uni.get("regionLogo", ""),
        "score": uni.get("score"),
        "indicators": {
            "world_class_faculty": uni.get("36"),
            "world_class_output": uni.get("37"),
            "high_quality_research": uni.get("38"),
            "research_impact": uni.get("39"),
            "international_collaboration": uni.get("40"),
        },
        "indicator_details": uni.get("indData", {}),
    }


async def fetch_main_payload(client: httpx.AsyncClient, build_hash: str, year: int) -> Dict[str, Any]:
    """Fetch the main GRAS payload containing subject and year info."""
    payload_url = f"{BASE_URL}/_nuxt/static/{build_hash}/rankings/gras/{year}/payload.js"
    resp = await client.get(payload_url)
    resp.raise_for_status()
    
    data = parse_nuxt_payload(resp.text)
    return data.get("data", [{}])[0]


async def fetch_subject_rankings(
    client: httpx.AsyncClient, 
    build_hash: str, 
    year: int, 
    subject_code: str
) -> Dict[str, Any]:
    """Fetch rankings for a specific subject."""
    payload_url = f"{BASE_URL}/_nuxt/static/{build_hash}/rankings/gras/{year}/{subject_code}/payload.js"
    resp = await client.get(payload_url)
    resp.raise_for_status()
    
    data = parse_nuxt_payload(resp.text)
    return data.get("data", [{}])[0]


async def list_subjects(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    List all available academic subjects with their codes.
    
    Args:
        params: May contain 'year' (int, optional) for reference year
        ctx: Context (unused)
    
    Returns:
        Dictionary with subject categories and their subjects
    """
    year = params.get("year", 2025)
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            build_hash = await get_build_hash(client)
            main_data = await fetch_main_payload(client, build_hash, year)
            
            categories = []
            all_subjects = []
            
            for cat in main_data.get("subjData", []):
                cat_name = cat.get("nameEn", "").strip()
                subjects = []
                
                for sub in cat.get("detail", []):
                    subject_info = {
                        "code": sub.get("code", ""),
                        "name": sub.get("nameEn", ""),
                        "available_years": sub.get("versions", "").split(",") if sub.get("versions") else [],
                    }
                    subjects.append(subject_info)
                    all_subjects.append({
                        **subject_info,
                        "category": cat_name,
                    })
                
                categories.append({
                    "name": cat_name,
                    "subject_count": len(subjects),
                    "subjects": subjects,
                })
            
            return {
                "success": True,
                "year": year,
                "total_subjects": len(all_subjects),
                "categories": categories,
                "available_years": [y["value"] for y in main_data.get("yearList", [])],
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }


async def get_rankings(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Get university rankings for a specific academic subject.
    
    Args:
        params: Must contain 'subject_code' (str), may contain 'year' (int), 
                'limit' (int), 'offset' (int)
        ctx: Context (unused)
    
    Returns:
        Dictionary with ranking results
    """
    subject_code = params.get("subject_code")
    if not subject_code:
        return {
            "success": False,
            "error": "subject_code is required",
            "error_type": "ValidationError",
        }
    
    year = params.get("year", 2024)
    limit = params.get("limit", 100)
    offset = params.get("offset", 0)
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            build_hash = await get_build_hash(client)
            subject_data = await fetch_subject_rankings(client, build_hash, year, subject_code)
            
            # Get subject info from main payload
            main_data = await fetch_main_payload(client, build_hash, year)
            subject_name = None
            subject_category = None
            
            for cat in main_data.get("subjData", []):
                for sub in cat.get("detail", []):
                    if sub.get("code") == subject_code:
                        subject_name = sub.get("nameEn")
                        subject_category = cat.get("nameEn", "").strip()
                        break
                if subject_name:
                    break
            
            # Process universities
            univ_list = subject_data.get("univList", [])
            total_count = len(univ_list)
            
            # Apply pagination
            paginated = univ_list[offset:offset + limit]
            
            rankings = [process_ranking_data(uni) for uni in paginated]
            
            return {
                "success": True,
                "year": year,
                "subject": {
                    "code": subject_code,
                    "name": subject_name,
                    "category": subject_category,
                },
                "total_results": total_count,
                "offset": offset,
                "limit": limit,
                "returned_count": len(rankings),
                "rankings": rankings,
                "columns": subject_data.get("columns", []),
                "indicators": subject_data.get("indList", []),
            }
            
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP error {e.response.status_code}: {e.response.url}",
                "error_type": "HTTPError",
                "subject_code": subject_code,
                "year": year,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }


async def search_universities(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Search for universities by name within rankings.
    
    Args:
        params: Must contain 'query' (str), may contain 'subject_code' (str), 'year' (int)
        ctx: Context (unused)
    
    Returns:
        Dictionary with matching universities
    """
    query = params.get("query", "").lower()
    if not query:
        return {
            "success": False,
            "error": "query is required",
            "error_type": "ValidationError",
        }
    
    year = params.get("year", 2024)
    subject_code = params.get("subject_code")
    limit = params.get("limit", 50)
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            build_hash = await get_build_hash(client)
            
            # If subject_code provided, search only that subject
            if subject_code:
                subject_data = await fetch_subject_rankings(client, build_hash, year, subject_code)
                univ_list = subject_data.get("univList", [])
                
                results = []
                for uni in univ_list:
                    name = uni.get("univNameEn", "").lower()
                    if query in name:
                        results.append(process_ranking_data(uni))
                        if len(results) >= limit:
                            break
                
                return {
                    "success": True,
                    "query": query,
                    "subject_code": subject_code,
                    "year": year,
                    "total_matches": len(results),
                    "results": results,
                }
            
            # Otherwise, get subjects and search across them
            main_data = await fetch_main_payload(client, build_hash, year)
            
            all_results = []
            searched_subjects = []
            
            for cat in main_data.get("subjData", []):
                for sub in cat.get("detail", []):
                    code = sub.get("code")
                    try:
                        subject_data = await fetch_subject_rankings(client, build_hash, year, code)
                        univ_list = subject_data.get("univList", [])
                        
                        for uni in univ_list:
                            name = uni.get("univNameEn", "").lower()
                            if query in name:
                                result = process_ranking_data(uni)
                                result["subject"] = {
                                    "code": code,
                                    "name": sub.get("nameEn"),
                                    "category": cat.get("nameEn", "").strip(),
                                }
                                all_results.append(result)
                        
                        searched_subjects.append(code)
                        
                        if len(all_results) >= limit:
                            break
                            
                    except Exception:
                        continue
                
                if len(all_results) >= limit:
                    break
            
            return {
                "success": True,
                "query": query,
                "year": year,
                "searched_subjects": searched_subjects,
                "total_matches": len(all_results[:limit]),
                "results": all_results[:limit],
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the Shanghai Ranking GRAS skill.
    
    Args:
        params: Dictionary containing:
            - function: One of 'list_subjects', 'get_rankings', 'search_universities'
            - Additional parameters specific to each function
        ctx: Context (unused)
    
    Returns:
        Dictionary with function results
    """
    function = params.get("function")
    
    if not function:
        return {
            "success": False,
            "error": "function parameter is required",
            "error_type": "ValidationError",
            "available_functions": ["list_subjects", "get_rankings", "search_universities"],
        }
    
    handlers = {
        "list_subjects": list_subjects,
        "get_rankings": get_rankings,
        "search_universities": search_universities,
    }
    
    handler = handlers.get(function)
    if not handler:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "error_type": "ValidationError",
            "available_functions": list(handlers.keys()),
        }
    
    return await handler(params, ctx)