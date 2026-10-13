"""
SearchOS Access Skill for www.dota2.com

This skill extracts structured content from:
- News entries (e.g., /newsentry/{id})
- Tournament bracket pages (e.g., /tournaments/international2012/...)
"""

import re
import json
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute Dota2.com content extraction.
    
    Args:
        params: Dictionary containing:
            - function: One of 'get_news_entry', 'get_tournament_bracket', 'get_tournament_game'
            - url: The URL to fetch (for all functions)

    
    Returns:
        Dictionary with extracted structured content or error information
    """
    function = params.get("function", "")
    
    try:
        if function == "get_news_entry":
            return await _get_news_entry(params)
        elif function == "get_tournament_bracket":
            return await _get_tournament_bracket(params)
        elif function == "get_tournament_game":
            return await _get_tournament_game(params)
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}",
                "available_functions": ["get_news_entry", "get_tournament_bracket", "get_tournament_game"]
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


async def _get_news_entry(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract news entry content from a Dota2 news page.
    
    Args:
        params: Must contain 'url' with the news entry URL

    
    Returns:
        Dictionary with news entry data: title, date, content, image_url, etc.
    """
    url = params.get("url", "")
    if not url:
        return {"success": False, "error": "Missing required parameter: url"}
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(5000)  # Wait for React rendering
            
            html = await page.content()
            
            # Extract meta tags
            og_title = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            og_desc = re.search(r'<meta property="og:description" content="([^"]+)"', html)
            og_image = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            
            # Extract title from page
            title = og_title.group(1) if og_title else ""
            if not title:
                title_match = re.search(r'<title>([^<]+)</title>', html)
                title = title_match.group(1).strip() if title_match else ""
            
            # Extract description/content
            description = og_desc.group(1) if og_desc else ""
            image_url = og_image.group(1) if og_image else ""
            
            # Extract date from the content div
            # Pattern: <div class="_2JNhX...">November 1, 2022</div>
            date_match = re.search(r'<div class="[^"]*_2JNhX[^"]*"[^>]*>([^<]+)</div>', html)
            date = date_match.group(1).strip() if date_match else ""
            
            # Extract main content
            # The content is in a div with class containing _30GVv
            content_match = re.search(r'<div class="[^"]*_30GVv[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            content = ""
            if content_match:
                content_html = content_match.group(1)
                # Clean up HTML tags
                content = re.sub(r'<br\s*/?>', '\n', content_html)
                content = re.sub(r'<[^>]+>', ' ', content)
                content = re.sub(r'\s+', ' ', content).strip()
            
            # Extract news ID from URL
            news_id_match = re.search(r'/newsentry/(\d+)', url)
            news_id = news_id_match.group(1) if news_id_match else ""
            
            # Get the full visible text as fallback
            body = await page.query_selector('body')
            full_text = ""
            if body:
                full_text = await body.evaluate('''el => {
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll('script, style, noscript').forEach(s => s.remove());
                    return clone.innerText;
                }''')
            
            return {
                "success": True,
                "data": {
                    "news_id": news_id,
                    "title": title,
                    "date": date,
                    "description": description,
                    "content": content if content else description,
                    "image_url": image_url,
                    "url": url,
                    "full_text": full_text[:5000] if full_text else ""
                }
            }
            
        finally:
            await browser.close()


async def _get_tournament_bracket(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract tournament bracket data from International 2012 pages.
    
    Args:
        params: Must contain 'url' with the tournament bracket URL

    
    Returns:
        Dictionary with bracket data: tournament_name, bracket_type, matches, etc.
    """
    url = params.get("url", "")
    if not url:
        return {"success": False, "error": "Missing required parameter: url"}
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)
            
            html = await page.content()
            page_url = page.url
            page_title = await page.title()
            
            # Determine bracket type from URL
            bracket_type = "unknown"
            if "grandfinal" in url.lower():
                bracket_type = "grand_final"
            elif "winners" in url.lower():
                bracket_type = "winners_bracket"
            elif "losers" in url.lower():
                bracket_type = "losers_bracket"
            
            # Extract tournament info from title
            tournament_name = ""
            if "International 2012" in page_title:
                tournament_name = "The International 2012"
            elif "International" in page_title:
                tournament_name = page_title.split(" - ")[0] if " - " in page_title else page_title
            
            # Parse matches based on bracket type
            matches = []
            
            if bracket_type == "grand_final":
                matches = _parse_grand_final_matches(html)
            elif bracket_type == "winners_bracket":
                matches = _parse_winners_bracket(html)
            elif bracket_type == "losers_bracket":
                matches = _parse_losers_bracket(html)
            
            # Extract team logos
            team_logos = {}
            logo_pattern = r'<img src="([^"]*international2012/teams/([^"]+)\.png)"'
            for match in re.finditer(logo_pattern, html):
                logo_url = match.group(1)
                team_key = match.group(2)
                team_logos[team_key] = logo_url
            
            return {
                "success": True,
                "data": {
                    "tournament_name": tournament_name,
                    "bracket_type": bracket_type,
                    "matches": matches,
                    "team_logos": team_logos,
                    "url": url,
                    "final_url": page_url,
                    "page_title": page_title
                }
            }
            
        finally:
            await browser.close()


def _parse_grand_final_matches(html: str) -> list[dict]:
    """Parse grand final matches from HTML."""
    matches = []
    
    # Pattern for grand final games
    # Each game has two team blocks with results and a game block with link
    game_pattern = re.compile(
        r'<div class="finalsTeamBlock[^"]*"[^>]*>.*?'
        r'<div class="resultsBlockText[^"]*">([^<]+)</div>.*?'
        r'<div class="blockResult">([WL])</div>.*?'
        r'</div>\s*'
        r'<div class="finalsGameBlock"[^>]*>.*?'
        r'Game\s+(\d+).*?'
        r'<a href="([^"]+)">View</a>.*?'
        r'</div>\s*'
        r'<div class="finalsTeamBlock[^"]*"[^>]*>.*?'
        r'<div class="resultsBlockText[^"]*">([^<]+)</div>.*?'
        r'<div class="blockResult">([WL])</div>',
        re.DOTALL
    )
    
    for match in game_pattern.finditer(html):
        team1, result1, game_num, game_url, team2, result2 = match.groups()
        
        # Determine winner
        winner = team2.strip() if result2 == 'W' else team1.strip()
        
        matches.append({
            "game": int(game_num),
            "team1": team1.strip(),
            "team1_result": result1,
            "team2": team2.strip(),
            "team2_result": result2,
            "winner": winner,
            "game_url": game_url
        })
    
    return matches


def _parse_winners_bracket(html: str) -> list[dict]:
    """Parse winners bracket from HTML."""
    matches = []
    
    # Pattern for team names in winners bracket
    # <div class="gameBlockTeamName" id="match1a_name"><nobr>LGD-GAMING</nobr></div>
    team_pattern = r'<div class="gameBlockTeamName"[^>]*id="match(\d+)([ab])_name"[^>]*><nobr>([^<]+)</nobr></div>'
    
    teams_by_match = {}
    for match in re.finditer(team_pattern, html):
        match_num = match.group(1)
        team_pos = match.group(2)  # 'a' or 'b'
        team_name = match.group(3).strip()
        
        if match_num not in teams_by_match:
            teams_by_match[match_num] = {}
        teams_by_match[match_num][team_pos] = team_name
    
    # Convert to matches list
    for match_num in sorted(teams_by_match.keys(), key=int):
        teams = teams_by_match[match_num]
        match_data = {
            "match_number": int(match_num),
            "team_a": teams.get('a', ''),
            "team_b": teams.get('b', '')
        }
        matches.append(match_data)
    
    return matches


def _parse_losers_bracket(html: str) -> list[dict]:
    """Parse losers bracket from HTML."""
    matches = []
    
    # Pattern for team names in losers bracket
    team_pattern = r'<div class="gameBlockTeamName"[^>]*id="match(\d+)([ab])_name"[^>]*><nobr>([^<]+)</nobr></div>'
    
    teams_by_match = {}
    for match in re.finditer(team_pattern, html):
        match_num = match.group(1)
        team_pos = match.group(2)  # 'a' or 'b'
        team_name = match.group(3).strip()
        
        if match_num not in teams_by_match:
            teams_by_match[match_num] = {}
        teams_by_match[match_num][team_pos] = team_name
    
    # Look for elimination information
    # Pattern: "Team Name eliminated Wins $X"
    elimination_pattern = r'([A-Za-z][A-Za-z\s\-\']+?)\s+eliminated\s+Wins\s+\$([\d,]+)'
    eliminations = {}
    for match in re.finditer(elimination_pattern, html):
        team_name = match.group(1).strip()
        prize = match.group(2)
        eliminations[team_name] = prize
    
    # Convert to matches list
    for match_num in sorted(teams_by_match.keys(), key=int):
        teams = teams_by_match[match_num]
        match_data = {
            "match_number": int(match_num),
            "team_a": teams.get('a', ''),
            "team_b": teams.get('b', '')
        }
        
        # Check if either team was eliminated
        for team in [teams.get('a', ''), teams.get('b', '')]:
            if team in eliminations:
                match_data["eliminated_team"] = team
                match_data["prize"] = eliminations[team]
                break
        
        matches.append(match_data)
    
    return matches


async def _get_tournament_game(params: dict[str, Any]) -> dict[str, Any]:
    """
    Extract individual tournament game details.
    
    Args:
        params: Must contain 'url' with the game URL (e.g., /tournaments/international2012/game/40/)

    
    Returns:
        Dictionary with game details
    """
    url = params.get("url", "")
    if not url:
        return {"success": False, "error": "Missing required parameter: url"}
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)
            
            html = await page.content()
            page_title = await page.title()
            
            # Extract game ID from URL
            game_id_match = re.search(r'/game/(\d+)', url)
            game_id = game_id_match.group(1) if game_id_match else ""
            
            # Get visible text
            body = await page.query_selector('body')
            visible_text = ""
            if body:
                visible_text = await body.evaluate('''el => {
                    const clone = el.cloneNode(true);
                    clone.querySelectorAll('script, style, noscript').forEach(s => s.remove());
                    return clone.innerText;
                }''')
            
            # Extract any video/replay links
            video_links = re.findall(r'href="([^"]*(?:youtube|twitch|video|replay)[^"]*)"', html, re.IGNORECASE)
            
            return {
                "success": True,
                "data": {
                    "game_id": game_id,
                    "url": url,
                    "title": page_title,
                    "video_links": list(set(video_links)),
                    "content": visible_text[:3000] if visible_text else ""
                }
            }
            
        finally:
            await browser.close()