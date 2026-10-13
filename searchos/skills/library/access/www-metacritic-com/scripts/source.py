"""
Metacritic Access Skill for SearchOS

Fetches TV show information, critic reviews, and details from Metacritic.
Uses Playwright to handle JavaScript rendering and extracts structured data
from JSON-LD schema and DOM elements.
"""

import json
import re
from typing import Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def _fetch_page(url: str, wait_ms: int = 5000) -> tuple[str, dict | None]:
    """Fetch a page and return its HTML content and JSON-LD data."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except PlaywrightTimeoutError:
                # Continue anyway - page might have loaded enough
                pass
            
            await page.wait_for_timeout(wait_ms)
            
            html = await page.content()
            
            # Extract JSON-LD
            jsonld_data = None
            jsonld_script = await page.query_selector('script[type="application/ld+json"]')
            if jsonld_script:
                try:
                    jsonld_text = await jsonld_script.inner_text()
                    jsonld_data = json.loads(jsonld_text)
                except (json.JSONDecodeError, Exception):
                    pass
            
            return html, jsonld_data
            
        finally:
            await browser.close()


def _parse_score_text(text: str) -> dict:
    """Parse score section text to extract score, sentiment, and count."""
    result = {
        "score": None,
        "sentiment": None,
        "count": None
    }
    
    # Extract score (first number)
    score_match = re.search(r'(\d+(?:\.\d+)?)', text)
    if score_match:
        result["score"] = float(score_match.group(1))
        if result["score"] == int(result["score"]):
            result["score"] = int(result["score"])
    
    # Extract count (e.g., "Based on 29 Critic Reviews")
    count_match = re.search(r'Based on (\d+)', text, re.IGNORECASE)
    if count_match:
        result["count"] = int(count_match.group(1))
    
    # Extract sentiment (e.g., "Universal Acclaim", "Generally Favorable")
    sentiments = [
        "Universal Acclaim", "Generally Favorable", "Mixed or Average Reviews",
        "Generally Unfavorable Reviews", "Overwhelming Dislike"
    ]
    for sentiment in sentiments:
        if sentiment.lower() in text.lower():
            result["sentiment"] = sentiment
            break
    
    return result


def _safe_get_creators(creator_data) -> list:
    """Safely extract creator names from JSON-LD data."""
    if creator_data is None:
        return []
    if isinstance(creator_data, list):
        return [c.get("name") for c in creator_data if isinstance(c, dict) and c.get("name")]
    if isinstance(creator_data, dict):
        name = creator_data.get("name")
        return [name] if name else []
    return []


def _safe_get_list(data, key) -> list:
    """Safely get a list from JSON-LD data."""
    value = data.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _safe_get_nested_names(data, key) -> list:
    """Safely extract names from a list of dicts in JSON-LD data."""
    value = data.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return [item.get("name") for item in value if isinstance(item, dict) and item.get("name")]
    if isinstance(value, dict):
        name = value.get("name")
        return [name] if name else []
    return []


async def _get_tv_show_info(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch TV show information from Metacritic."""
    show_slug = params.get("show_slug", "").strip("/")
    if not show_slug:
        return {"error": "show_slug parameter is required"}
    
    url = f"https://www.metacritic.com/tv/{show_slug}/"
    
    try:
        html, jsonld_data = await _fetch_page(url)
        
        if not jsonld_data:
            return {"error": "Could not extract show data from page", "url": url}
        
        # Build result from JSON-LD with safe extraction
        result = {
            "url": url,
            "title": jsonld_data.get("name"),
            "type": jsonld_data.get("@type"),
            "description": jsonld_data.get("description"),
            "image": jsonld_data.get("image"),
            "content_rating": jsonld_data.get("contentRating"),
            "date_published": jsonld_data.get("datePublished"),
            "genres": _safe_get_list(jsonld_data, "genre"),
            "number_of_seasons": jsonld_data.get("numberOfSeasons"),
            "awards": _safe_get_list(jsonld_data, "award"),
            "creators": _safe_get_creators(jsonld_data.get("creator")),
            "production_companies": _safe_get_nested_names(jsonld_data, "productionCompany"),
            "actors": _safe_get_nested_names(jsonld_data, "actor"),
            "metascore": None,
            "metascore_details": None,
            "trailer": None
        }
        
        # Extract metascore from aggregateRating
        agg_rating = jsonld_data.get("aggregateRating", {})
        if agg_rating:
            result["metascore"] = agg_rating.get("ratingValue")
            result["metascore_details"] = {
                "score": agg_rating.get("ratingValue"),
                "review_count": agg_rating.get("reviewCount"),
                "best_rating": agg_rating.get("bestRating"),
                "worst_rating": agg_rating.get("worstRating"),
                "description": agg_rating.get("description"),
                "reviews_url": agg_rating.get("url")
            }
        
        # Extract trailer info
        trailer = jsonld_data.get("trailer", {})
        if trailer:
            result["trailer"] = {
                "name": trailer.get("name"),
                "duration": trailer.get("duration"),
                "upload_date": trailer.get("uploadDate"),
                "content_url": trailer.get("contentUrl"),
                "embed_url": trailer.get("embedUrl")
            }
        
        return result
        
    except Exception as e:
        return {"error": f"Failed to fetch show info: {str(e)}", "url": url}


async def _get_critic_reviews(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch critic reviews for a TV show from Metacritic."""
    show_slug = params.get("show_slug", "").strip("/")
    if not show_slug:
        return {"error": "show_slug parameter is required"}
    
    url = f"https://www.metacritic.com/tv/{show_slug}/critic-reviews/"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )
                page = await context.new_page()
                
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    pass
                
                await page.wait_for_timeout(5000)
                
                # Extract show title
                title = await page.title()
                
                # Get overall score from hero section
                overall_score = None
                hero_score_el = await page.query_selector('.c-siteReviewScore_background-critic_large')
                if hero_score_el:
                    score_text = await hero_score_el.inner_text()
                    try:
                        overall_score = int(score_text.strip())
                    except ValueError:
                        pass
                
                # Extract review cards
                reviews = []
                review_cards = await page.query_selector_all('[data-testid="review-card"]')
                
                for card in review_cards:
                    review = {}
                    
                    # Date
                    date_el = await card.query_selector('[data-testid="review-card-date"]')
                    if date_el:
                        review["date"] = (await date_el.inner_text()).strip()
                    
                    # Score
                    score_el = await card.query_selector('.c-siteReviewScore_background')
                    if score_el:
                        score_text = await score_el.inner_text()
                        try:
                            review["score"] = int(score_text.strip())
                        except ValueError:
                            review["score"] = score_text.strip()
                    
                    # Extract publication and author from full text
                    full_text = await card.inner_text()
                    lines = [l.strip() for l in full_text.split('\n') if l.strip()]
                    
                    # Find publication (usually after score)
                    for i, line in enumerate(lines):
                        # Skip date and score lines
                        if re.match(r'^[A-Z]{2,3}\s+\d{1,2},?\s+\d{4}$', line):
                            continue
                        if line.isdigit() and len(line) <= 3:
                            continue
                        # Publication is usually the line after score
                        if review.get("score") is not None and i > 0:
                            if not line.startswith("By ") and "REVIEW" not in line:
                                review["publication"] = line
                                break
                    
                    # Author
                    author_el = await card.query_selector('[class*="review-footer"] span, [class*="author"]')
                    if author_el:
                        author_text = await author_el.inner_text()
                        if author_text.startswith("By "):
                            review["author"] = author_text[3:].strip()
                        else:
                            review["author"] = author_text.strip()
                    else:
                        # Try to find "By X" pattern
                        for line in lines:
                            if line.startswith("By "):
                                review["author"] = line[3:].strip()
                                break
                    
                    # Quote/excerpt
                    quote_el = await card.query_selector('[data-testid="review-card-content"]')
                    if quote_el:
                        quote_text = await quote_el.inner_text()
                        # Remove date, score, publication from beginning
                        quote_lines = quote_text.split('\n')
                        # Usually the quote is the last substantial part
                        for line in reversed(quote_lines):
                            line = line.strip()
                            if line and not re.match(r'^[A-Z]{2,3}\s+\d{1,2},?\s+\d{4}$', line):
                                if not line.isdigit() and "REVIEW" not in line and not line.startswith("By "):
                                    if len(line) > 30:  # Reasonable quote length
                                        review["quote"] = line
                                        break
                    
                    # Link to full review
                    link_el = await card.query_selector('a[href*="review"]')
                    if link_el:
                        href = await link_el.get_attribute('href')
                        if href:
                            review["link"] = href if href.startswith('http') else f"https://www.metacritic.com{href}"
                    
                    if review.get("score") is not None:
                        reviews.append(review)
                
                return {
                    "url": url,
                    "title": title,
                    "show_slug": show_slug,
                    "overall_score": overall_score,
                    "review_count": len(reviews),
                    "reviews": reviews
                }
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {"error": f"Failed to fetch critic reviews: {str(e)}", "url": url}


async def _get_show_details(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch detailed TV show information including cast, crew, and metadata."""
    show_slug = params.get("show_slug", "").strip("/")
    if not show_slug:
        return {"error": "show_slug parameter is required"}
    
    url = f"https://www.metacritic.com/tv/{show_slug}/"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}
                )
                page = await context.new_page()
                
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeoutError:
                    pass
                
                await page.wait_for_timeout(5000)
                
                # Extract JSON-LD for comprehensive data
                jsonld_data = None
                jsonld_script = await page.query_selector('script[type="application/ld+json"]')
                if jsonld_script:
                    try:
                        jsonld_text = await jsonld_script.inner_text()
                        jsonld_data = json.loads(jsonld_text)
                    except:
                        pass
                
                if not jsonld_data:
                    return {"error": "Could not extract show details", "url": url}
                
                # Extract additional details from page with safe extraction
                details = {
                    "url": url,
                    "title": jsonld_data.get("name"),
                    "description": jsonld_data.get("description"),
                    "image": jsonld_data.get("image"),
                    "content_rating": jsonld_data.get("contentRating"),
                    "date_published": jsonld_data.get("datePublished"),
                    "genres": _safe_get_list(jsonld_data, "genre"),
                    "number_of_seasons": jsonld_data.get("numberOfSeasons"),
                    "awards": _safe_get_list(jsonld_data, "award"),
                    "creators": [],
                    "actors": [],
                    "production_companies": []
                }
                
                # Parse creators
                creators_data = jsonld_data.get("creator")
                if creators_data:
                    if isinstance(creators_data, list):
                        for creator in creators_data:
                            if isinstance(creator, dict):
                                details["creators"].append({
                                    "name": creator.get("name"),
                                    "url": creator.get("url"),
                                    "type": creator.get("@type")
                                })
                    elif isinstance(creators_data, dict):
                        details["creators"].append({
                            "name": creators_data.get("name"),
                            "url": creators_data.get("url"),
                            "type": creators_data.get("@type")
                        })
                
                # Parse actors
                actors_data = jsonld_data.get("actor")
                if actors_data:
                    if isinstance(actors_data, list):
                        for actor in actors_data:
                            if isinstance(actor, dict):
                                details["actors"].append({
                                    "name": actor.get("name"),
                                    "url": actor.get("url")
                                })
                    elif isinstance(actors_data, dict):
                        details["actors"].append({
                            "name": actors_data.get("name"),
                            "url": actors_data.get("url")
                        })
                
                # Parse production companies
                companies_data = jsonld_data.get("productionCompany")
                if companies_data:
                    if isinstance(companies_data, list):
                        for company in companies_data:
                            if isinstance(company, dict):
                                details["production_companies"].append(company.get("name"))
                    elif isinstance(companies_data, dict):
                        details["production_companies"].append(companies_data.get("name"))
                
                # Get metascore info
                agg_rating = jsonld_data.get("aggregateRating", {})
                if agg_rating:
                    details["metascore"] = {
                        "score": agg_rating.get("ratingValue"),
                        "review_count": agg_rating.get("reviewCount"),
                        "reviews_url": agg_rating.get("url")
                    }
                
                # Get trailer info
                trailer = jsonld_data.get("trailer", {})
                if trailer:
                    details["trailer"] = {
                        "name": trailer.get("name"),
                        "duration": trailer.get("duration"),
                        "upload_date": trailer.get("uploadDate"),
                        "content_url": trailer.get("contentUrl"),
                        "embed_url": trailer.get("embedUrl")
                    }
                
                # Extract user score from hero section using JavaScript
                hero_text = await page.evaluate('''
                    () => {
                        const heroEl = document.querySelector('[class*="hero-scores"], [class*="product-hero__scores"]');
                        return heroEl ? heroEl.innerText : null;
                    }
                ''')
                
                if hero_text:
                    # Parse user score from hero text
                    # Format: "User score\nGenerally Favorable\nBased on 558 User Ratings\n7.0"
                    lines = hero_text.split('\n')
                    for i, line in enumerate(lines):
                        if 'user score' in line.lower():
                            # Look for the score in subsequent lines
                            for j in range(i + 1, min(i + 5, len(lines))):
                                score_line = lines[j].strip()
                                if re.match(r'^\d+\.?\d*$', score_line):
                                    try:
                                        details["user_score"] = float(score_line)
                                        break
                                    except ValueError:
                                        pass
                            # Look for count
                            for j in range(i + 1, min(i + 5, len(lines))):
                                count_match = re.search(r'Based on (\d+)', lines[j], re.IGNORECASE)
                                if count_match:
                                    details["user_rating_count"] = int(count_match.group(1))
                                    break
                            break
                
                return details
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {"error": f"Failed to fetch show details: {str(e)}", "url": url}


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Metacritic access skill.
    
    Dispatches to the appropriate function based on params["function"].
    
    Functions:
        - get_tv_show_info: Get basic TV show information including metascore
        - get_critic_reviews: Get critic reviews for a TV show
        - get_show_details: Get detailed TV show information including cast and crew
    """
    function = params.get("function", "")
    
    if function == "get_tv_show_info":
        return await _get_tv_show_info(params)
    elif function == "get_critic_reviews":
        return await _get_critic_reviews(params)
    elif function == "get_show_details":
        return await _get_show_details(params)
    else:
        return {
            "error": f"Unknown function: {function}. Available functions: get_tv_show_info, get_critic_reviews, get_show_details"
        }