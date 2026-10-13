"""
Pati Jinich Recipe Extractor - SearchOS Access Skill

Extracts structured recipe data from patijinich.com using:
1. WordPress REST API (wprm_recipe endpoint) for recipe listings and search
2. JSON-LD structured data for individual recipe pages (fallback)
3. WPRM (WordPress Recipe Maker) embedded data in HTML

The site uses WP Recipe Maker plugin which provides:
- REST API at /wp-json/wp/v2/wprm_recipe
- JSON-LD structured data in HTML pages
- Taxonomies: wprm_course, wprm_cuisine, wprm_keyword
"""

import asyncio
import aiohttp
import re
import json
from typing import Any
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute recipe extraction from patijinich.com
    
    Functions:
    - get_recipe: Extract a single recipe by URL
    - search_recipes: Search recipes by keyword
    - list_recipes: List recipes with pagination and filtering
    - get_recipe_by_id: Get recipe by WPRM ID
    - list_cuisines: List available cuisine types
    - list_courses: List available course types
    """
    function = params.get("function", "")
    
    if function == "get_recipe":
        return await get_recipe(params)
    elif function == "search_recipes":
        return await search_recipes(params)
    elif function == "list_recipes":
        return await list_recipes(params)
    elif function == "get_recipe_by_id":
        return await get_recipe_by_id(params)
    elif function == "list_cuisines":
        return await list_cuisines(params)
    elif function == "list_courses":
        return await list_courses(params)
    else:
        return {"error": f"Unknown function: {function}", "success": False}


async def _fetch_html(url: str, timeout: int = 45) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            html = await response.text()
            return response.status, html


async def _fetch_json(url: str, timeout: int = 30) -> tuple[int, Any, dict]:
    """Fetch JSON content from a URL (for REST API)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
            data = await response.json()
            # Get pagination headers
            headers_dict = {
                "X-WP-Total": response.headers.get("X-WP-Total", "0"),
                "X-WP-TotalPages": response.headers.get("X-WP-TotalPages", "0"),
            }
            return response.status, data, headers_dict


def _parse_iso8601_duration(duration: str) -> dict:
    """Parse ISO 8601 duration (PT15M) to readable format."""
    if not duration:
        return {"raw": None, "minutes": 0, "readable": ""}
    
    hours = 0
    minutes = 0
    
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', duration)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
    
    total_minutes = hours * 60 + minutes
    
    if hours and minutes:
        readable = f"{hours}h {minutes}m"
    elif hours:
        readable = f"{hours} hour{'s' if hours > 1 else ''}"
    elif minutes:
        readable = f"{minutes} minute{'s' if minutes > 1 else ''}"
    else:
        readable = ""
    
    return {
        "raw": duration,
        "minutes": total_minutes,
        "readable": readable
    }


def _extract_recipe_from_jsonld(html: str) -> dict | None:
    """Extract recipe data from JSON-LD structured data."""
    json_ld_pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
    matches = re.findall(json_ld_pattern, html, re.DOTALL)
    
    for match in matches:
        try:
            data = json.loads(match)
            if '@graph' in data:
                for item in data['@graph']:
                    if item.get('@type') == 'Recipe':
                        return _parse_jsonld_recipe(item)
            elif data.get('@type') == 'Recipe':
                return _parse_jsonld_recipe(data)
        except json.JSONDecodeError:
            continue
    
    return None


def _parse_jsonld_recipe(item: dict) -> dict:
    """Parse JSON-LD Recipe object into structured data."""
    # Parse instructions
    instructions = []
    for section in item.get('recipeInstructions', []):
        if section.get('@type') == 'HowToSection':
            section_data = {
                "name": section.get('name', ''),
                "steps": []
            }
            for step in section.get('itemListElement', []):
                section_data["steps"].append(step.get('text', ''))
            instructions.append(section_data)
        elif section.get('@type') == 'HowToStep':
            instructions.append({
                "name": "",
                "steps": [section.get('text', '')]
            })
    
    # Parse rating
    rating = None
    if 'aggregateRating' in item:
        rating = {
            "average": float(item['aggregateRating'].get('ratingValue', 0)),
            "count": int(item['aggregateRating'].get('ratingCount', 0))
        }
    
    # Parse yield
    recipe_yield = item.get('recipeYield', [])
    if isinstance(recipe_yield, list):
        yield_str = recipe_yield[0] if recipe_yield else ""
    else:
        yield_str = str(recipe_yield)
    
    # Parse cuisine and category
    cuisine = item.get('recipeCuisine', [])
    if isinstance(cuisine, list):
        cuisine = cuisine[0] if cuisine else ""
    
    category = item.get('recipeCategory', [])
    if isinstance(category, list):
        category = category[0] if category else ""
    
    return {
        "name": item.get('name', ''),
        "description": item.get('description', ''),
        "yield": yield_str,
        "servings": yield_str,
        "prep_time": _parse_iso8601_duration(item.get('prepTime', '')),
        "cook_time": _parse_iso8601_duration(item.get('cookTime', '')),
        "total_time": _parse_iso8601_duration(item.get('totalTime', '')),
        "cuisine": cuisine,
        "category": category,
        "keywords": item.get('keywords', '').split(', ') if item.get('keywords') else [],
        "ingredients": item.get('recipeIngredient', []),
        "instructions": instructions,
        "rating": rating,
        "image": item.get('image', [''])[0] if item.get('image') else None,
        "date_published": item.get('datePublished', ''),
        "url": item.get('mainEntityOfPage', ''),
        "author": "Pati Jinich",
        "source": "json-ld"
    }


def _parse_wprm_recipe(recipe_data: dict) -> dict:
    """Parse WPRM REST API recipe data into structured format."""
    recipe = recipe_data.get('recipe', {})
    
    # Parse ingredients
    ingredients = []
    for group in recipe.get('ingredients', []):
        if 'ingredients' in group:
            for ing in group['ingredients']:
                amount = ing.get('amount', '')
                unit = ing.get('unit', '')
                name = ing.get('name', '')
                notes = ing.get('notes', '')
                
                ingredient_str = f"{amount} {unit} {name}".strip()
                if notes:
                    ingredient_str += f" ({notes})"
                ingredients.append(ingredient_str.strip())
    
    # Parse instructions
    instructions = []
    for group in recipe.get('instructions', []):
        section_data = {
            "name": group.get('name', ''),
            "steps": []
        }
        for step in group.get('instructions', []):
            # Clean HTML from text
            text = step.get('text', '')
            text = re.sub(r'<[^>]+>', '', text)
            section_data["steps"].append(text)
        if section_data["steps"]:
            instructions.append(section_data)
    
    # Parse tags
    tags = recipe.get('tags', {})
    cuisine = ""
    category = ""
    keywords = []
    
    if 'cuisine' in tags and tags['cuisine']:
        cuisine = tags['cuisine'][0].get('name', '')
    if 'course' in tags and tags['course']:
        category = tags['course'][0].get('name', '')
    if 'keyword' in tags and tags['keyword']:
        keywords = [k.get('name', '') for k in tags['keyword']]
    
    # Parse rating
    rating_data = recipe.get('rating', {})
    rating = None
    if rating_data and rating_data.get('count') and int(rating_data.get('count', 0)) > 0:
        rating = {
            "average": float(rating_data.get('average', 0)),
            "count": int(rating_data.get('count', 0))
        }
    
    # Parse times
    prep_time = recipe.get('prep_time', '0')
    cook_time = recipe.get('cook_time', '0')
    total_time = recipe.get('total_time', '0')
    
    # If total time is 0, calculate it
    if total_time == '0' or not total_time:
        total_minutes = int(prep_time or 0) + int(cook_time or 0)
    else:
        total_minutes = int(total_time)
    
    return {
        "id": recipe_data.get('id'),
        "name": recipe.get('name', ''),
        "description": re.sub(r'<[^>]+>', '', recipe.get('summary', '')),
        "yield": f"{recipe.get('servings', '')} {recipe.get('servings_unit', '')}".strip(),
        "servings": f"{recipe.get('servings', '')} {recipe.get('servings_unit', '')}".strip(),
        "prep_time": {
            "minutes": int(prep_time or 0),
            "readable": f"{prep_time} minutes" if prep_time else ""
        },
        "cook_time": {
            "minutes": int(cook_time or 0),
            "readable": f"{cook_time} minutes" if cook_time else ""
        },
        "total_time": {
            "minutes": total_minutes,
            "readable": f"{total_minutes} minutes" if total_minutes else ""
        },
        "cuisine": cuisine,
        "category": category,
        "keywords": keywords,
        "ingredients": ingredients,
        "instructions": instructions,
        "rating": rating,
        "image": recipe.get('image_url'),
        "date_published": recipe_data.get('date', ''),
        "url": recipe_data.get('link', ''),
        "author": "Pati Jinich",
        "source": "wprm-api"
    }


async def get_recipe(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract a single recipe from a patijinich.com URL.
    
    Parameters:
    - url: The recipe URL (required)
    """
    url = params.get("url", "").strip()
    
    if not url:
        return {"error": "URL is required", "success": False}
    
    if "patijinich.com" not in url:
        return {"error": "URL must be from patijinich.com", "success": False}
    
    try:
        status, html = await _fetch_html(url)
        
        if status != 200:
            return {"error": f"Failed to fetch page (status {status})", "success": False}
        
        # Try JSON-LD first
        recipe = _extract_recipe_from_jsonld(html)
        
        if recipe:
            return {
                "success": True,
                "recipe": recipe,
                "source": "json-ld"
            }
        
        # If no JSON-LD, try to find WPRM recipe ID in URL and use API
        # Extract post slug from URL
        slug_match = re.search(r'patijinich\.com/([^/]+)/?$', url)
        if slug_match:
            slug = slug_match.group(1)
            # Try to find recipe via API
            api_url = f"https://patijinich.com/wp-json/wp/v2/wprm_recipe?slug=wprm-{slug}&per_page=1"
            try:
                status, data, _ = await _fetch_json(api_url)
                if status == 200 and data:
                    recipe = _parse_wprm_recipe(data[0])
                    return {
                        "success": True,
                        "recipe": recipe,
                        "source": "wprm-api"
                    }
            except Exception:
                pass
        
        return {"error": "No recipe data found on page", "success": False}
    
    except asyncio.TimeoutError:
        return {"error": "Request timed out", "success": False}
    except Exception as e:
        return {"error": f"Failed to extract recipe: {str(e)}", "success": False}


async def get_recipe_by_id(params: dict[str, Any]) -> dict[str, Any]:
    """
    Get a recipe by its WPRM ID.
    
    Parameters:
    - recipe_id: The WPRM recipe ID (required)
    """
    recipe_id = params.get("recipe_id")
    
    if not recipe_id:
        return {"error": "recipe_id is required", "success": False}
    
    try:
        api_url = f"https://patijinich.com/wp-json/wp/v2/wprm_recipe/{recipe_id}"
        status, data, _ = await _fetch_json(api_url)
        
        if status == 200 and data:
            recipe = _parse_wprm_recipe(data)
            return {
                "success": True,
                "recipe": recipe
            }
        
        return {"error": f"Recipe not found (status {status})", "success": False}
    
    except Exception as e:
        return {"error": f"Failed to fetch recipe: {str(e)}", "success": False}


async def search_recipes(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search recipes by keyword.
    
    Parameters:
    - query: Search query (required)
    - page: Page number (default: 1)
    - per_page: Results per page (default: 10, max: 50)
    """
    query = params.get("query", "").strip()
    page = int(params.get("page", 1))
    per_page = min(int(params.get("per_page", 10)), 50)
    
    if not query:
        return {"error": "Search query is required", "success": False}
    
    try:
        # Use posts endpoint with search and recipe category
        api_url = f"https://patijinich.com/wp-json/wp/v2/posts?search={query}&categories=327&page={page}&per_page={per_page}"
        status, data, headers = await _fetch_json(api_url)
        
        if status != 200:
            return {"error": f"Search failed (status {status})", "success": False}
        
        # Extract basic info and fetch full recipe data
        results = []
        for post in data:
            # Get the recipe ID from the post (it links to wprm_recipe)
            recipe_url = post.get('link', '')
            
            # Try to get recipe data from the URL
            try:
                _, html = await _fetch_html(recipe_url)
                recipe = _extract_recipe_from_jsonld(html)
                if recipe:
                    results.append({
                        "id": post.get('id'),
                        "title": post.get('title', {}).get('rendered', ''),
                        "url": recipe_url,
                        "recipe": recipe,
                        "date": post.get('date', '')
                    })
            except Exception:
                # Just include basic info
                results.append({
                    "id": post.get('id'),
                    "title": post.get('title', {}).get('rendered', ''),
                    "url": recipe_url,
                    "date": post.get('date', '')
                })
        
        return {
            "success": True,
            "query": query,
            "results": results,
            "total": int(headers.get('X-WP-Total', 0)),
            "total_pages": int(headers.get('X-WP-TotalPages', 0)),
            "current_page": page,
            "per_page": per_page
        }
    
    except Exception as e:
        return {"error": f"Search failed: {str(e)}", "success": False}


async def list_recipes(params: dict[str, Any]) -> dict[str, Any]:
    """
    List recipes with pagination and filtering options.
    
    Parameters:
    - page: Page number (default: 1)
    - per_page: Results per page (default: 10, max: 50)
    - cuisine: Filter by cuisine (e.g., "Mexican")
    - course: Filter by course (e.g., "Dessert")
    - keyword: Filter by keyword
    """
    page = int(params.get("page", 1))
    per_page = min(int(params.get("per_page", 10)), 50)
    cuisine = params.get("cuisine", "").strip()
    course = params.get("course", "").strip()
    keyword = params.get("keyword", "").strip()
    
    try:
        # Build API URL
        api_url = f"https://patijinich.com/wp-json/wp/v2/wprm_recipe?page={page}&per_page={per_page}"
        
        # Add filters if provided
        if cuisine:
            # Get cuisine ID
            cuisine_api = f"https://patijinich.com/wp-json/wp/v2/wprm_cuisine?search={cuisine}"
            _, cuisines, _ = await _fetch_json(cuisine_api)
            if cuisines:
                api_url += f"&wprm_cuisine={cuisines[0]['id']}"
        
        if course:
            # Get course ID
            course_api = f"https://patijinich.com/wp-json/wp/v2/wprm_course?search={course}"
            _, courses, _ = await _fetch_json(course_api)
            if courses:
                api_url += f"&wprm_course={courses[0]['id']}"
        
        if keyword:
            # Get keyword ID
            keyword_api = f"https://patijinich.com/wp-json/wp/v2/wprm_keyword?search={keyword}"
            _, keywords, _ = await _fetch_json(keyword_api)
            if keywords:
                api_url += f"&wprm_keyword={keywords[0]['id']}"
        
        status, data, headers = await _fetch_json(api_url)
        
        if status != 200:
            return {"error": f"Failed to list recipes (status {status})", "success": False}
        
        results = []
        for recipe_data in data:
            recipe = _parse_wprm_recipe(recipe_data)
            results.append(recipe)
        
        return {
            "success": True,
            "results": results,
            "total": int(headers.get('X-WP-Total', 0)),
            "total_pages": int(headers.get('X-WP-TotalPages', 0)),
            "current_page": page,
            "per_page": per_page
        }
    
    except Exception as e:
        return {"error": f"Failed to list recipes: {str(e)}", "success": False}


async def list_cuisines(params: dict[str, Any]) -> dict[str, Any]:
    """
    List all available cuisine types for filtering.
    """
    try:
        api_url = "https://patijinich.com/wp-json/wp/v2/wprm_cuisine?per_page=100"
        status, data, _ = await _fetch_json(api_url)
        
        if status != 200:
            return {"error": f"Failed to list cuisines (status {status})", "success": False}
        
        cuisines = [
            {
                "id": c.get('id'),
                "name": c.get('name'),
                "slug": c.get('slug'),
                "count": c.get('count', 0)
            }
            for c in data
        ]
        
        return {
            "success": True,
            "cuisines": cuisines
        }
    
    except Exception as e:
        return {"error": f"Failed to list cuisines: {str(e)}", "success": False}


async def list_courses(params: dict[str, Any]) -> dict[str, Any]:
    """
    List all available course types for filtering.
    """
    try:
        api_url = "https://patijinich.com/wp-json/wp/v2/wprm_course?per_page=100"
        status, data, _ = await _fetch_json(api_url)
        
        if status != 200:
            return {"error": f"Failed to list courses (status {status})", "success": False}
        
        courses = [
            {
                "id": c.get('id'),
                "name": c.get('name'),
                "slug": c.get('slug'),
                "count": c.get('count', 0)
            }
            for c in data
        ]
        
        return {
            "success": True,
            "courses": courses
        }
    
    except Exception as e:
        return {"error": f"Failed to list courses: {str(e)}", "success": False}