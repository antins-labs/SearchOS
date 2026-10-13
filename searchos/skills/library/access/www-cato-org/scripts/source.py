"""
Cato Institute People Profile Scraper
Extracts biographical and professional information from Cato Institute expert profiles.
"""

from playwright.async_api import async_playwright
import json
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Cato Institute people profile extraction.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with extracted data or error information
    """
    function = params.get("function")
    
    if function == "get_person_profile":
        return await get_person_profile(params)
    elif function == "search_people":
        return await search_people(params)
    else:
        return {"error": f"Unknown function: {function}"}


async def get_person_profile(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract profile data for a specific person from Cato Institute.
    
    Args:
        params: Must contain 'url' or 'slug' parameter
    
    Returns:
        Dictionary with person profile data
    """
    url = params.get("url")
    slug = params.get("slug")
    
    if not url and not slug:
        return {"error": "Either 'url' or 'slug' parameter is required"}
    
    if slug and not url:
        # Construct URL from slug
        slug = slug.strip("/")
        url = f"https://www.cato.org/people/{slug}"
    
    if not url.startswith("https://www.cato.org/people/"):
        return {"error": "URL must be a Cato Institute people profile page (https://www.cato.org/people/...)"}
    
    result = await fetch_person_profile(url)
    return result


async def search_people(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for people on Cato Institute website.
    
    Args:
        params: Must contain 'query' parameter with search term
    
    Returns:
        Dictionary with search results
    """
    query = params.get("query", "").strip()
    
    if not query:
        return {"error": "Search 'query' parameter is required"}
    
    # Cato uses Algolia for search
    search_url = f"https://www.cato.org/search?keys={query}"
    
    results = await fetch_search_results(search_url, query)
    return results


async def fetch_person_profile(url: str) -> dict[str, Any]:
    """
    Fetch and parse a person's profile page using Playwright.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York',
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                }
            )
            
            page = await context.new_page()
            
            # Hide webdriver property
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            except Exception as e:
                # Continue even if timeout - page might still have useful content
                pass
            
            # Wait for content to load
            await page.wait_for_timeout(5000)
            
            # Check if we hit a block page
            html = await page.content()
            if 'Incapsula' in html and 'incident_id' in html:
                return {
                    "error": "Access blocked by Incapsula security. Please try again later.",
                    "url": url
                }
            
            # Extract data from JSON-LD structured data
            profile_data = await page.evaluate('''() => {
                const result = {
                    url: window.location.href,
                    success: false
                };
                
                // Extract JSON-LD data
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const script of scripts) {
                    try {
                        const data = JSON.parse(script.textContent);
                        if (data['@graph']) {
                            for (const item of data['@graph']) {
                                if (item['@type'] === 'Person') {
                                    result.name = item.name || '';
                                    result.first_name = item.givenName || '';
                                    result.last_name = item.familyName || '';
                                    result.position = item.jobTitle || '';
                                    result.email = item.email || '';
                                    result.description = item.description || '';
                                    result.image_url = item.image ? item.image.url : '';
                                    result.social_links = item.sameAs || [];
                                    result.success = true;
                                    break;
                                }
                            }
                        }
                    } catch (e) {}
                }
                
                // Extract meta tags as backup
                if (!result.name) {
                    const ogTitle = document.querySelector('meta[property="og:title"]');
                    if (ogTitle) result.name = ogTitle.content;
                }
                
                if (!result.first_name) {
                    const firstName = document.querySelector('meta[property="profile:first_name"]');
                    if (firstName) result.first_name = firstName.content;
                }
                
                if (!result.last_name) {
                    const lastName = document.querySelector('meta[property="profile:last_name"]');
                    if (lastName) result.last_name = lastName.content;
                }
                
                if (!result.image_url) {
                    const ogImage = document.querySelector('meta[property="og:image"]');
                    if (ogImage) result.image_url = ogImage.content;
                }
                
                // Extract visible bio text
                const bioSelectors = [
                    '.field--name-field-bio',
                    '.bio', 
                    '.biography',
                    '.field--name-body'
                ];
                
                for (const sel of bioSelectors) {
                    const elem = document.querySelector(sel);
                    if (elem) {
                        const text = elem.innerText.trim();
                        if (text && text.length > 50) {
                            result.bio = text;
                            break;
                        }
                    }
                }
                
                // If no bio found, try to get first few paragraphs from main content
                if (!result.bio) {
                    const main = document.querySelector('main, article, .layout-content');
                    if (main) {
                        const paragraphs = main.querySelectorAll('p');
                        const bioTexts = [];
                        for (const p of paragraphs) {
                            const text = p.innerText.trim();
                            if (text && text.length > 50 && !text.includes('Skip to')) {
                                bioTexts.push(text);
                                if (bioTexts.length >= 3) break;
                            }
                        }
                        if (bioTexts.length > 0) {
                            result.bio = bioTexts.join(' ');
                        }
                    }
                }
                
                // Extract phone number
                const phoneLink = document.querySelector('a[href^="tel:"]');
                if (phoneLink) {
                    result.phone = phoneLink.innerText.trim();
                }
                
                // Extract email from page content (if not in JSON-LD)
                if (!result.email) {
                    const emailLink = document.querySelector('a[href^="mailto:"]');
                    if (emailLink) {
                        result.email = emailLink.innerText.trim() || emailLink.href.replace('mailto:', '');
                    }
                }
                
                // Extract recent publications/articles
                const publications = [];
                const pubSelectors = [
                    '.views-row',
                    '.publication-item',
                    'article.node--type-publication',
                    '.node--type-blog',
                    '.views-view-grid .views-col'
                ];
                
                for (const sel of pubSelectors) {
                    const items = document.querySelectorAll(sel);
                    if (items.length > 0) {
                        items.forEach((item, i) => {
                            if (i < 10) {
                                const titleElem = item.querySelector('h3, h4, .field--name-title, a');
                                const linkElem = item.querySelector('a[href*="/publications/"], a[href*="/blog/"], a[href*="/commentary/"]');
                                if (titleElem) {
                                    const title = titleElem.innerText.trim();
                                    const link = linkElem ? linkElem.href : '';
                                    if (title && title.length > 5 && !publications.find(function(p) { return p.title === title; })) {
                                        publications.push({
                                            title: title,
                                            url: link
                                        });
                                    }
                                }
                            }
                        });
                        if (publications.length > 0) break;
                    }
                }
                
                if (publications.length > 0) {
                    result.recent_publications = publications;
                }
                
                // Extract areas of expertise/topics
                const topics = [];
                const topicSelectors = [
                    '.field--name-field-topics a',
                    '.field--name-field-issues a',
                    '.tags a'
                ];
                
                for (const sel of topicSelectors) {
                    const links = document.querySelectorAll(sel);
                    links.forEach(function(link) {
                        const text = link.innerText.trim();
                        if (text && text.length > 2 && !topics.includes(text)) {
                            topics.push(text);
                        }
                    });
                }
                
                if (topics.length > 0) {
                    result.expertise_areas = topics;
                }
                
                // Set success flag if we got at least a name
                if (result.name) {
                    result.success = true;
                }
                
                return result;
            }''')
            
            return profile_data
            
        except Exception as e:
            return {
                "error": f"Failed to fetch profile: {str(e)}",
                "url": url
            }
        finally:
            await browser.close()


async def fetch_search_results(search_url: str, query: str) -> dict[str, Any]:
    """
    Fetch search results from Cato Institute website.
    Note: This is a basic implementation that scrapes the search page.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York',
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
            )
            
            page = await context.new_page()
            
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)
            
            try:
                await page.goto(search_url, wait_until='domcontentloaded', timeout=45000)
            except:
                pass
            
            await page.wait_for_timeout(5000)
            
            # Extract search results
            results = await page.evaluate('''() => {
                const items = [];
                
                // Look for search result items
                const resultSelectors = [
                    '.search-result',
                    '.views-row',
                    'article',
                    '.result-item'
                ];
                
                for (const sel of resultSelectors) {
                    const elements = document.querySelectorAll(sel);
                    if (elements.length > 0) {
                        elements.forEach(function(elem, i) {
                            if (i < 20) {
                                const titleElem = elem.querySelector('h3, h2, .title, a');
                                const linkElem = elem.querySelector('a');
                                const descElem = elem.querySelector('p, .description, .summary');
                                
                                if (titleElem && linkElem) {
                                    const title = titleElem.innerText.trim();
                                    const link = linkElem.href;
                                    const desc = descElem ? descElem.innerText.trim() : '';
                                    
                                    // Check if it's a person profile
                                    const isPerson = link.includes('/people/');
                                    
                                    if (title && link) {
                                        items.push({
                                            title: title,
                                            url: link,
                                            description: desc.substring(0, 300),
                                            type: isPerson ? 'person' : 'publication'
                                        });
                                    }
                                }
                            }
                        });
                        break;
                    }
                }
                
                const urlParams = new URLSearchParams(window.location.search);
                const queryParam = urlParams.get('keys') || '';
                
                return {
                    query: queryParam,
                    results: items,
                    total: items.length
                };
            }''')
            
            results['search_url'] = search_url
            return results
            
        except Exception as e:
            return {
                "error": f"Search failed: {str(e)}",
                "query": query,
                "search_url": search_url
            }
        finally:
            await browser.close()