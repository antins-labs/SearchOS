"""
FilmAffinity Awards History Access Skill

Fetches award history data from FilmAffinity (www.filmaffinity.com).
The site requires JavaScript rendering, so Playwright is used for access.

Available functions:
- get_award_history: Get all winners for a specific award category
- get_categories: List available award categories for a festival
"""

from __future__ import annotations
import asyncio
import re
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the FilmAffinity awards history skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ('get_award_history' or 'get_categories')
            - category_id: Award category ID (e.g., 'berlin_best_actor')
            - include_empty: Whether to include years without winners (default: False)

    
    Returns:
        Dictionary with results or error information
    """
    function = params.get("function")
    
    if function == "get_award_history":
        category_id = params.get("category_id")
        if not category_id:
            return {"error": "Missing required parameter: category_id"}
        
        include_empty = params.get("include_empty", False)
        return await get_award_history(category_id, include_empty)
    
    elif function == "get_categories":
        category_id = params.get("category_id", "berlin_best_actor")
        return await get_categories(category_id)
    
    else:
        return {"error": f"Unknown function: {function}. Available: get_award_history, get_categories"}


async def get_award_history(category_id: str, include_empty: bool = False) -> dict[str, Any]:
    """
    Fetch award history for a specific category.
    
    Args:
        category_id: The award category ID (e.g., 'berlin_best_actor', 'berlin_golden_bear')
        include_empty: Whether to include years without winners
    
    Returns:
        Dictionary with award history data
    """
    from playwright.async_api import async_playwright
    
    url = f"https://www.filmaffinity.com/en/awards-history.php?cat-id={category_id}"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()
                
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(2)  # Allow JS to render
                
                # Extract page title and award info
                page_info = await page.evaluate('''
                    () => {
                        const h1 = document.querySelector('h1#main-title');
                        return {
                            title: h1 ? h1.textContent.trim() : null,
                            url: window.location.href
                        };
                    }
                ''')
                
                # Extract award history data - handles both person awards (like Best Actor)
                # and movie awards (like Best Picture)
                award_data = await page.evaluate('''
                    (includeEmpty) => {
                        const results = [];
                        const rows = document.querySelectorAll('.awards-history-page .row.border-bottom');
                        
                        for (const row of rows) {
                            // Get year
                            const yearLink = row.querySelector('.year a');
                            if (!yearLink) continue;
                            
                            const year = yearLink.textContent.trim();
                            const editionUrl = yearLink.href;
                            const editionIdMatch = yearLink.href.match(/edition-id=([^&]+)/);
                            const editionId = editionIdMatch ? editionIdMatch[1] : null;
                            
                            // Check if empty row
                            const isEmpty = row.classList.contains('empty-row');
                            
                            // Skip empty rows if not requested
                            if (isEmpty && !includeEmpty) continue;
                            
                            // Get winners
                            const winners = [];
                            const winnersDiv = row.querySelector('.winners');
                            
                            if (winnersDiv && !isEmpty) {
                                // Case 1: Person awards (Best Actor, Best Director, etc.)
                                // Structure: .winner-card containing .name-text with person name
                                const personCards = winnersDiv.querySelectorAll('.winner-card');
                                
                                if (personCards.length > 0) {
                                    for (const card of personCards) {
                                        // Get person name
                                        const nameTextDiv = card.querySelector('.name-text a');
                                        const personName = nameTextDiv ? nameTextDiv.textContent.trim() : null;
                                        const personUrl = nameTextDiv ? nameTextDiv.href : null;
                                        const personIdMatch = personUrl ? personUrl.match(/name-id=(\\d+)/) : null;
                                        const personId = personIdMatch ? personIdMatch[1] : null;
                                        
                                        // Get movie info
                                        const movieLink = card.querySelector('.name-winner-movie');
                                        const movieUrl = movieLink ? movieLink.href : null;
                                        const movieIdMatch = movieUrl ? movieUrl.match(/movie-id=(\\d+)/) : null;
                                        const movieId = movieIdMatch ? movieIdMatch[1] : null;
                                        
                                        // Movie title from alt attribute
                                        const movieImg = card.querySelector('.mc-poster img');
                                        const movieTitle = movieImg ? movieImg.getAttribute('alt').trim() : null;
                                        
                                        // Get nominations/awards count
                                        const nomText = card.textContent;
                                        const nomMatch = nomText.match(/(\\d+)\\s*nominations?\\s*(\\d+)\\s*awards?/i);
                                        let nominations = null, awards = null;
                                        if (nomMatch) {
                                            nominations = parseInt(nomMatch[1]);
                                            awards = parseInt(nomMatch[2]);
                                        }
                                        
                                        if (personName) {
                                            winners.push({
                                                type: 'person',
                                                name: personName,
                                                person_id: personId,
                                                person_url: personUrl,
                                                movie: movieTitle,
                                                movie_id: movieId,
                                                movie_url: movieUrl,
                                                nominations: nominations,
                                                awards: awards
                                            });
                                        }
                                    }
                                }
                                
                                // Case 2: Movie awards (Best Picture, etc.)
                                // Structure: .fa-card.aw-mc-new containing movie info directly
                                const movieCards = winnersDiv.querySelectorAll('.fa-card.aw-mc-new');
                                
                                if (movieCards.length > 0) {
                                    for (const card of movieCards) {
                                        // Get movie title
                                        const movieTitleLink = card.querySelector('.movie-title-link a');
                                        const movieTitle = movieTitleLink ? movieTitleLink.textContent.trim() : null;
                                        
                                        // Get movie URL and ID
                                        const movieUrl = movieTitleLink ? movieTitleLink.href : null;
                                        const movieIdMatch = movieUrl ? movieUrl.match(/movie-id=(\\d+)/) : null;
                                        const movieId = movieIdMatch ? movieIdMatch[1] : null;
                                        
                                        // Get country flag if available
                                        const countryImg = card.querySelector('.nflag');
                                        const country = countryImg ? countryImg.getAttribute('alt') : null;
                                        
                                        // Check for documentary label
                                        const typeSpan = card.querySelector('.type');
                                        const isDocumentary = typeSpan && typeSpan.textContent.toLowerCase().includes('documentary');
                                        
                                        // Get nominations/awards count
                                        const nomText = card.textContent;
                                        const nomMatch = nomText.match(/(\\d+)\\s*nominations?\\s*(\\d+)\\s*awards?/i);
                                        let nominations = null, awards = null;
                                        if (nomMatch) {
                                            nominations = parseInt(nomMatch[1]);
                                            awards = parseInt(nomMatch[2]);
                                        }
                                        
                                        if (movieTitle) {
                                            winners.push({
                                                type: 'movie',
                                                movie: movieTitle,
                                                movie_id: movieId,
                                                movie_url: movieUrl,
                                                country: country,
                                                is_documentary: isDocumentary || null,
                                                nominations: nominations,
                                                awards: awards
                                            });
                                        }
                                    }
                                }
                            }
                            
                            results.push({
                                year: parseInt(year),
                                edition_id: editionId,
                                edition_url: editionUrl,
                                is_empty: isEmpty,
                                winners: winners
                            });
                        }
                        
                        return results;
                    }
                ''', include_empty)
                
                # Sort by year descending
                award_data.sort(key=lambda x: x['year'], reverse=True)
                
                # Count statistics
                total_years = len(award_data)
                years_with_winners = sum(1 for y in award_data if y['winners'])
                total_winners = sum(len(y['winners']) for y in award_data)
                
                # Determine award type
                award_type = 'unknown'
                if award_data:
                    for y in award_data:
                        if y['winners']:
                            award_type = y['winners'][0].get('type', 'unknown')
                            break
                
                return {
                    "success": True,
                    "category_id": category_id,
                    "category_title": page_info['title'],
                    "award_type": award_type,
                    "url": page_info['url'],
                    "statistics": {
                        "total_years": total_years,
                        "years_with_winners": years_with_winners,
                        "total_winner_entries": total_winners
                    },
                    "years": award_data
                }
                
            finally:
                await browser.close()
                
    except asyncio.TimeoutError:
        return {"error": "Timeout while loading page", "category_id": category_id}
    except Exception as e:
        return {"error": f"Failed to fetch award history: {str(e)}", "category_id": category_id}


async def get_categories(category_id: str = "berlin_best_actor") -> dict[str, Any]:
    """
    List available award categories for a festival.
    
    Uses an existing category page to discover all categories in that festival.
    
    Args:
        category_id: Any valid category ID from the festival to discover
    
    Returns:
        Dictionary with available categories
    """
    from playwright.async_api import async_playwright
    
    url = f"https://www.filmaffinity.com/en/awards-history.php?cat-id={category_id}"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    viewport={'width': 1920, 'height': 1080}
                )
                page = await context.new_page()
                
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await asyncio.sleep(2)
                
                # Get page title and all categories
                data = await page.evaluate('''
                    () => {
                        const h1 = document.querySelector('h1#main-title');
                        
                        // Extract festival name from title
                        let festival = null;
                        if (h1) {
                            const title = h1.textContent.trim();
                            const parts = title.split(' - ');
                            if (parts.length > 0) {
                                festival = parts[0].trim();
                            }
                        }
                        
                        // Get all category links
                        const links = document.querySelectorAll('a[href*="cat-id="]');
                        const categories = [];
                        const seen = new Set();
                        
                        for (const link of links) {
                            const catIdMatch = link.href.match(/cat-id=([^&]+)/);
                            if (catIdMatch) {
                                const id = catIdMatch[1];
                                if (!seen.has(id)) {
                                    seen.add(id);
                                    categories.push({
                                        id: id,
                                        name: link.textContent.trim(),
                                        url: link.href
                                    });
                                }
                            }
                        }
                        
                        return {
                            title: h1 ? h1.textContent.trim() : null,
                            festival: festival,
                            categories: categories
                        };
                    }
                ''')
                
                return {
                    "success": True,
                    "festival": data['festival'],
                    "page_title": data['title'],
                    "url": url,
                    "total_categories": len(data['categories']),
                    "categories": data['categories']
                }
                
            finally:
                await browser.close()
                
    except asyncio.TimeoutError:
        return {"error": "Timeout while loading page", "category_id": category_id}
    except Exception as e:
        return {"error": f"Failed to fetch categories: {str(e)}", "category_id": category_id}