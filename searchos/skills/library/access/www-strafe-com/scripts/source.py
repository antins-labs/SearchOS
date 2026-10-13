"""
Strafe.com News Access Skill

Fetches esports news articles from Strafe.com, with specialized extraction
for award/roster announcements containing structured player and team data.
"""

from __future__ import annotations

import re
from typing import Any

from playwright.async_api import async_playwright


async def _fetch_and_extract(url: str, extract_fn, wait_ms: int = 3000) -> dict:
    """Fetch a page and extract data in a single browser session.
    
    Args:
        url: URL to fetch
        extract_fn: JavaScript function string to evaluate on the page
        wait_ms: Milliseconds to wait after page load
    
    Returns:
        Extracted data as dict
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()
            
            try:
                await page.goto(url, wait_until="load", timeout=60000)
            except Exception:
                # Continue even if timeout - page often loads enough content
                pass
            
            await page.wait_for_timeout(wait_ms)
            
            data = await page.evaluate(extract_fn)
            data["url"] = page.url
            
            return data
        finally:
            await browser.close()


# JavaScript extraction functions

NEWS_LIST_EXTRACTOR = """
() => {
    const results = [];
    const seen = new Set();
    
    const links = document.querySelectorAll("a[href*='/news/read/']");
    
    links.forEach(link => {
        const href = link.href;
        if (seen.has(href)) return;
        seen.add(href);
        
        // Find container
        let container = link;
        for (let i = 0; i < 5; i++) {
            const parent = container.parentElement;
            if (!parent) break;
            if (parent.querySelector('img')) {
                container = parent;
                break;
            }
            container = parent;
        }
        
        // Title
        let title = '';
        const heading = container.querySelector('h2, h3, h4');
        if (heading) {
            title = heading.textContent.trim();
        } else {
            title = link.textContent.trim();
        }
        
        // Image
        const img = container.querySelector('img');
        const imageUrl = img ? (img.src || img.dataset.src || '') : '';
        
        // Category
        const categoryEl = container.querySelector('[class*="game"]') ||
                          container.querySelector('[class*="sport"]') ||
                          container.querySelector('[class*="category"]');
        const category = categoryEl ? categoryEl.textContent.trim() : '';
        
        // Date
        const dateEl = container.querySelector('time') ||
                      container.querySelector('[class*="date"]');
        const dateText = dateEl ? dateEl.textContent.trim() : '';
        
        // Excerpt
        const excerptEl = container.querySelector('p');
        const excerpt = excerptEl ? excerptEl.textContent.trim().substring(0, 200) : '';
        
        if (title || href) {
            results.push({
                title,
                url: href,
                imageUrl,
                category,
                date: dateText,
                excerpt
            });
        }
    });
    
    return { articles: results };
}
"""

ARTICLE_EXTRACTOR = """
() => {
    const result = {};
    
    // Title
    const h1 = document.querySelector('h1');
    result.title = h1 ? h1.textContent.trim() : '';
    
    // Meta description
    const metaDesc = document.querySelector('meta[name="description"]');
    result.description = metaDesc ? metaDesc.content : '';
    
    // Author - look for common patterns
    const authorEl = document.querySelector('[class*="author"]') || 
                    document.querySelector('a[href*="/author/"]');
    result.author = authorEl ? authorEl.textContent.trim() : '';
    
    // Date
    const dateEl = document.querySelector('time') || 
                  document.querySelector('[class*="date"]');
    result.date = dateEl ? (dateEl.getAttribute('datetime') || dateEl.textContent.trim()) : '';
    
    // Article body - get all paragraphs
    const article = document.querySelector('article');
    if (article) {
        const paragraphs = Array.from(article.querySelectorAll('p'))
            .map(p => p.textContent.trim())
            .filter(t => t.length > 20);
        result.content = paragraphs;
    } else {
        result.content = [];
    }
    
    // Extract player mentions with links
    result.players = [];
    const playerLinks = document.querySelectorAll('a[href*="/player/"]');
    const seenPlayers = new Set();
    playerLinks.forEach(link => {
        const name = link.textContent.trim();
        const href = link.href;
        if (name && !seenPlayers.has(name)) {
            seenPlayers.add(name);
            result.players.push({ name, url: href });
        }
    });
    
    // Extract team mentions with links
    result.teams = [];
    const teamLinks = document.querySelectorAll('a[href*="/team/"]');
    const seenTeams = new Set();
    teamLinks.forEach(link => {
        const name = link.textContent.trim();
        const href = link.href;
        if (name && !seenTeams.has(name)) {
            seenTeams.add(name);
            result.teams.push({ name, url: href });
        }
    });
    
    return result;
}
"""

AWARDS_EXTRACTOR = """
() => {
    const result = {
        title: '',
        description: '',
        awards: {},
        players: [],
        teams: []
    };
    
    // Title
    const h1 = document.querySelector('h1');
    result.title = h1 ? h1.textContent.trim() : '';
    
    // Meta description
    const metaDesc = document.querySelector('meta[name="description"]');
    result.description = metaDesc ? metaDesc.content : '';
    
    // Extract awards by finding h3 headers followed by lists
    const h3s = document.querySelectorAll('h3');
    const processedAwards = new Set();
    
    h3s.forEach(h3 => {
        const text = h3.textContent.trim();
        
        // Check if this looks like an award category
        const awardPatterns = [
            /MVP/i, /Team/i, /Rookie/i, /Coaching/i, /Best/i,
            /All-\\w+\\s+Team/i, /Award/i, /Winner/i, /Final/i
        ];
        
        const isAward = awardPatterns.some(pattern => pattern.test(text));
        
        if (isAward && !processedAwards.has(text)) {
            const awardName = text.replace(/:$/, '').trim();
            processedAwards.add(text);
            result.awards[awardName] = [];
            
            // Get following ul elements
            let nextEl = h3.nextElementSibling;
            while (nextEl && (nextEl.tagName === 'UL' || nextEl.tagName === 'OL')) {
                const lis = nextEl.querySelectorAll('li');
                lis.forEach(li => {
                    const liText = li.textContent.trim();
                    if (liText) {
                        result.awards[awardName].push(liText);
                    }
                });
                nextEl = nextEl.nextElementSibling;
            }
            
            // Remove empty awards
            if (result.awards[awardName].length === 0) {
                delete result.awards[awardName];
            }
        }
    });
    
    // Extract players with structured data
    const playerLinks = document.querySelectorAll('a[href*="/player/"]');
    const seenPlayers = new Map();
    
    playerLinks.forEach(link => {
        const name = link.textContent.trim();
        const href = link.href;
        if (name && !seenPlayers.has(name)) {
            // Try to extract team from context
            let team = '';
            let role = '';
            
            const parentLi = link.closest('li');
            if (parentLi) {
                const liText = parentLi.textContent;
                
                // Try to find team code in parentheses like (TES), (IG), etc.
                const teamMatch = liText.match(/\\(([A-Z]{2,4})\\)/);
                if (teamMatch) {
                    team = teamMatch[1];
                }
                
                // Try to find role like "Top:", "ADC:", etc.
                const roleMatch = liText.match(/^(Top|Jungle|Mid|ADC|Support|Coach|Manager):/i);
                if (roleMatch) {
                    role = roleMatch[1];
                }
            }
            
            seenPlayers.set(name, {
                name,
                url: href,
                team,
                role
            });
        }
    });
    
    result.players = Array.from(seenPlayers.values());
    
    // Extract teams
    const teamLinks = document.querySelectorAll('a[href*="/team/"]');
    const seenTeams = new Map();
    
    teamLinks.forEach(link => {
        const name = link.textContent.trim();
        const href = link.href;
        if (name && !seenTeams.has(name)) {
            seenTeams.set(name, { name, url: href });
        }
    });
    
    result.teams = Array.from(seenTeams.values());
    
    return result;
}
"""


async def get_news_list(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch list of news articles from Strafe.com.
    
    Returns:
        dict with 'articles' list containing title, url, excerpt, etc.
    """
    url = "https://www.strafe.com/news/"
    
    try:
        data = await _fetch_and_extract(url, NEWS_LIST_EXTRACTOR)
        articles = data.get("articles", [])
        
        return {
            "success": True,
            "url": data.get("url", url),
            "article_count": len(articles),
            "articles": articles[:20],  # Limit to 20 articles
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "articles": [],
        }


async def get_article(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch a single news article from Strafe.com.
    
    Args:
        url: Full URL or slug of the article (e.g., 'jackeylove-takes-the-crown-...')
    
    Returns:
        dict with title, description, author, date, content, players, teams
    """
    url = params.get("url", "")
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url",
        }
    
    # Construct full URL if only slug provided
    if not url.startswith("http"):
        # Ensure slug format
        slug = url.strip("/")
        url = f"https://www.strafe.com/news/read/{slug}/"
    
    try:
        data = await _fetch_and_extract(url, ARTICLE_EXTRACTOR)
        
        return {
            "success": True,
            **data,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def get_awards_article(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch an awards/roster announcement article with structured extraction.
    
    Specialized for articles containing:
    - MVP awards
    - All-pro/all-star teams
    - Tournament rosters
    - Coaching staff announcements
    
    Args:
        url: Full URL or slug of the article
    
    Returns:
        dict with title, awards (dict), players (list with roles/teams), teams
    """
    url = params.get("url", "")
    
    if not url:
        return {
            "success": False,
            "error": "Missing required parameter: url",
        }
    
    # Construct full URL if only slug provided
    if not url.startswith("http"):
        slug = url.strip("/")
        url = f"https://www.strafe.com/news/read/{slug}/"
    
    try:
        data = await _fetch_and_extract(url, AWARDS_EXTRACTOR)
        
        # Calculate summary stats
        award_count = len(data.get("awards", {}))
        player_count = len(data.get("players", []))
        team_count = len(data.get("teams", []))
        
        return {
            "success": True,
            "award_count": award_count,
            "player_count": player_count,
            "team_count": team_count,
            **data,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """Main entry point for Strafe.com news access skill.
    
    Dispatches based on params["function"]:
        - get_news_list: Fetch list of recent news articles
        - get_article: Fetch a single article by URL/slug
        - get_awards_article: Fetch article with structured award/player extraction
    """
    function = params.get("function", "")
    
    if function == "get_news_list":
        return await get_news_list(params)
    elif function == "get_article":
        return await get_article(params)
    elif function == "get_awards_article":
        return await get_awards_article(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}. "
                    "Available: get_news_list, get_article, get_awards_article",
        }