"""
Rick Bayless Recipe Site Access Skill
Fetches recipe details from www.rickbayless.com
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Any
import json


async def fetch_html(url: str) -> tuple[int, str]:
    """Fetch HTML content from a URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            html = await response.text()
            return response.status, html


def parse_recipe(html: str, url: str) -> dict[str, Any]:
    """Parse recipe details from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Title
    title_el = soup.find('h1')
    title = title_el.get_text(strip=True) if title_el else ''
    
    # Description
    desc_div = soup.find(class_='recipe-description')
    description = desc_div.get_text(strip=True) if desc_div else ''
    
    # Image - prefer og:image for reliability
    og_image = soup.find('meta', property='og:image')
    image_url = og_image.get('content', '') if og_image else ''
    
    # Fallback to data-src on lazy-loaded image
    if not image_url:
        hero_img = soup.find('img', id='recipe-image')
        if hero_img:
            image_url = hero_img.get('data-src', '') or hero_img.get('src', '')
    
    # Ingredients
    ingredients = []
    ing_list = soup.select('.recipe-ingredients li[itemprop="ingredients"]')
    for li in ing_list:
        qty_span = li.find(class_='recipe-ingredient-quantity')
        unit_span = li.find(class_='recipe-ingredient-unit')
        name_span = li.find(class_='recipe-ingredient-name')
        notes_span = li.find(class_='recipe-ingredient-notes')
        
        ingredient = {
            'quantity': qty_span.get_text(strip=True) if qty_span else '',
            'unit': unit_span.get_text(strip=True) if unit_span else '',
            'name': name_span.get_text(strip=True) if name_span else '',
            'notes': notes_span.get_text(strip=True) if notes_span else '',
            'full_text': li.get_text(strip=True)
        }
        ingredients.append(ingredient)
    
    # Instructions
    instructions = []
    instructions_div = soup.find(class_='recipe-instructions')
    if instructions_div:
        for p in instructions_div.find_all('p'):
            text = p.get_text(strip=True)
            # Skip empty paragraphs, the "INSTRUCTIONS" header, and YouTube embeds
            if text and not text == 'INSTRUCTIONS' and 'youtube' not in str(p).lower():
                instructions.append(text)
    
    # Category/Term (recipe type)
    term_div = soup.find(class_='recipe-term')
    category = ''
    if term_div:
        # Get the term name from the link if present
        term_link = term_div.find('a')
        if term_link:
            category = term_link.get_text(strip=True)
        else:
            category = term_div.get_text(strip=True)
    
    return {
        'title': title,
        'description': description,
        'image_url': image_url,
        'category': category,
        'ingredients': ingredients,
        'instructions': instructions,
        'ingredient_count': len(ingredients),
        'instruction_count': len(instructions),
        'url': url
    }


def parse_recipe_list(html: str) -> list[dict[str, str]]:
    """Parse recipe listing page for recipe URLs."""
    soup = BeautifulSoup(html, 'html.parser')
    recipes = []
    seen_urls = set()
    
    # Find all recipe links
    for link in soup.select('a[href*="/recipe/"]'):
        href = link.get('href', '')
        # Skip the main recipe listing page
        if href == 'https://www.rickbayless.com/recipe/':
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)
        
        # Get link text as title hint
        text = link.get_text(strip=True)
        
        recipes.append({
            'url': href,
            'title_hint': text if text else None
        })
    
    return recipes


async def get_recipe(url: str) -> dict[str, Any]:
    """Fetch and parse a single recipe."""
    try:
        status, html = await fetch_html(url)
        
        if status == 404:
            return {'error': 'Recipe not found', 'error_code': 'NOT_FOUND', 'url': url}
        
        if status != 200:
            return {'error': f'Failed to fetch recipe (status {status})', 'error_code': 'FETCH_ERROR', 'url': url}
        
        recipe = parse_recipe(html, url)
        
        if not recipe['title']:
            return {'error': 'Could not parse recipe data', 'error_code': 'PARSE_ERROR', 'url': url}
        
        return recipe
        
    except Exception as e:
        return {'error': str(e), 'error_code': 'EXCEPTION', 'url': url}


async def list_recipes(page: int = 1) -> dict[str, Any]:
    """Fetch list of recipes from the recipe index."""
    try:
        url = "https://www.rickbayless.com/recipe/"
        status, html = await fetch_html(url)
        
        if status != 200:
            return {'error': f'Failed to fetch recipe list (status {status})', 'error_code': 'FETCH_ERROR'}
        
        recipes = parse_recipe_list(html)
        
        return {
            'recipes': recipes,
            'count': len(recipes),
            'page': page,
            'source_url': url
        }
        
    except Exception as e:
        return {'error': str(e), 'error_code': 'EXCEPTION'}


async def search_recipes(query: str) -> dict[str, Any]:
    """Search for recipes using the site's search."""
    try:
        # Use WordPress search endpoint
        url = f"https://www.rickbayless.com/?s={query}&post_type=recipe"
        status, html = await fetch_html(url)
        
        if status != 200:
            return {'error': f'Search failed (status {status})', 'error_code': 'FETCH_ERROR', 'query': query}
        
        recipes = parse_recipe_list(html)
        
        return {
            'recipes': recipes,
            'count': len(recipes),
            'query': query,
            'source_url': url
        }
        
    except Exception as e:
        return {'error': str(e), 'error_code': 'EXCEPTION', 'query': query}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Rick Bayless recipe skill functions.
    
    Functions:
        - get_recipe: Fetch a single recipe by URL
        - list_recipes: Get a list of recipes from the index
        - search_recipes: Search for recipes by keyword
    """
    function = params.get('function', '')
    
    if function == 'get_recipe':
        url = params.get('url', '')
        if not url:
            return {'error': 'Missing required parameter: url', 'error_code': 'MISSING_PARAM'}
        
        # Validate URL is from the expected domain
        if 'rickbayless.com/recipe/' not in url:
            return {'error': 'URL must be a rickbayless.com recipe URL', 'error_code': 'INVALID_URL'}
        
        return await get_recipe(url)
    
    elif function == 'list_recipes':
        page = params.get('page', 1)
        return await list_recipes(page)
    
    elif function == 'search_recipes':
        query = params.get('query', '')
        if not query:
            return {'error': 'Missing required parameter: query', 'error_code': 'MISSING_PARAM'}
        return await search_recipes(query)
    
    else:
        return {'error': f'Unknown function: {function}', 'error_code': 'UNKNOWN_FUNCTION'}


# For testing
if __name__ == '__main__':
    async def test():
        print("=== Test 1: Get Recipe ===")
        result = await execute({
            'function': 'get_recipe',
            'url': 'https://www.rickbayless.com/recipe/gaspacho-moreliano/'
        })
        print(json.dumps(result, indent=2))
        
        print("\n=== Test 2: List Recipes ===")
        result = await execute({
            'function': 'list_recipes'
        })
        print(json.dumps(result, indent=2)[:1000])
        
        print("\n=== Test 3: Search Recipes ===")
        result = await execute({
            'function': 'search_recipes',
            'query': 'tacos'
        })
        print(json.dumps(result, indent=2)[:1000])
    
    asyncio.run(test())