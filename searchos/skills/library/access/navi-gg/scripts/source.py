"""
SearchOS Access Skill for navi.gg tournament pages.

This skill extracts tournament information and match data from navi.gg,
specifically for NAVI (Natus Vincere) esports tournaments.

The site uses Cloudflare protection, so Playwright browser automation is required.
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright, Page


async def execute(params: Dict[str, Any], ctx=None) -> Dict[str, Any]:
    """
    Execute the navi.gg skill.
    
    Args:
        params: Dictionary containing:
            - function: The function to call ('get_tournament_info' or 'get_matches')
            - tournament_slug: The tournament slug (e.g., 'blasttv-austin-major-2025')
            - limit: Optional limit for number of matches to return (default: 50)

    
    Returns:
        Dictionary with tournament or match data
    """
    function = params.get("function")
    tournament_slug = params.get("tournament_slug")
    limit = params.get("limit", 50)
    
    if not function:
        return {"error": "Missing required parameter: function"}
    
    if not tournament_slug:
        return {"error": "Missing required parameter: tournament_slug"}
    
    # Clean the tournament slug
    tournament_slug = tournament_slug.strip("/")
    
    if function == "get_tournament_info":
        return await get_tournament_info(tournament_slug)
    elif function == "get_matches":
        return await get_matches(tournament_slug, limit)
    else:
        return {"error": f"Unknown function: {function}"}


async def get_tournament_info(tournament_slug: str) -> Dict[str, Any]:
    """
    Get tournament overview information.
    
    Args:
        tournament_slug: The tournament slug (e.g., 'blasttv-austin-major-2025')
    
    Returns:
        Dictionary with tournament information
    """
    url = f"https://navi.gg/en/tournaments/{tournament_slug}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # Navigate with timeout handling
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            except Exception:
                pass  # Continue even if timeout, page may have loaded
            
            # Wait for Cloudflare challenge to resolve
            await asyncio.sleep(3)
            
            # Check if we're on the right page
            title = await page.title()
            if 'Just a moment' in title:
                # Wait longer for challenge
                await asyncio.sleep(5)
            
            # Extract tournament info from JSON-LD
            scripts = await page.query_selector_all('script[type="application/ld+json"]')
            
            tournament_data = {
                'slug': tournament_slug,
                'url': url
            }
            
            for script in scripts:
                content = await script.inner_text()
                if content.strip():
                    try:
                        data = json.loads(content)
                        if data.get('@type') == 'SportsEvent':
                            tournament_data['name'] = data.get('name')
                            tournament_data['sport'] = data.get('sport')
                            tournament_data['description'] = data.get('description')
                            tournament_data['startDate'] = data.get('startDate')
                            tournament_data['endDate'] = data.get('endDate')
                            tournament_data['eventStatus'] = data.get('eventStatus', '').replace('https://schema.org/', '')
                            tournament_data['image'] = data.get('image')
                            break
                    except json.JSONDecodeError:
                        continue
            
            # Extract prize pool
            prize_elem = await page.query_selector('[class*="prize"]')
            if prize_elem:
                prize_text = await prize_elem.inner_text()
                # Extract prize amount
                prize_match = re.search(r'\$[\d,]+', prize_text)
                if prize_match:
                    tournament_data['prizePool'] = prize_match.group()
                # Check if LAN
                if 'LAN' in prize_text:
                    tournament_data['eventType'] = 'LAN'
            
            # Extract location from date element
            date_elems = await page.query_selector_all('[class*="date"]')
            for elem in date_elems:
                text = await elem.inner_text()
                # Look for location pattern (e.g., "Austin, United States")
                location_match = re.search(r'\n\s*([A-Z][^,\n]+,\s*[A-Za-z\s]+)', text)
                if location_match:
                    tournament_data['location'] = location_match.group(1).strip()
                    break
            
            # Extract page title for additional info
            page_title = await page.title()
            tournament_data['pageTitle'] = page_title
            
            # Check if tournament is finished
            finished_elem = await page.query_selector(':text("FINISHED")')
            if finished_elem:
                tournament_data['status'] = 'finished'
            else:
                # Check for live matches
                live_elem = await page.query_selector('.live')
                if live_elem:
                    tournament_data['status'] = 'live'
                else:
                    tournament_data['status'] = 'scheduled'
            
            return {"success": True, "data": tournament_data}
            
        finally:
            await browser.close()


async def get_matches(tournament_slug: str, limit: int = 50) -> Dict[str, Any]:
    """
    Get matches for a tournament.
    
    Args:
        tournament_slug: The tournament slug (e.g., 'blasttv-austin-major-2025')
        limit: Maximum number of matches to return
    
    Returns:
        Dictionary with matches data
    """
    url = f"https://navi.gg/en/tournaments/{tournament_slug}/matches"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            # Navigate with timeout handling
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            except Exception:
                pass  # Continue even if timeout
            
            # Wait for page to load
            await asyncio.sleep(3)
            
            # Extract match items
            match_items = await page.query_selector_all('.match-item')
            
            matches = []
            for item in match_items[:limit]:
                try:
                    match_data = {}
                    
                    # Get team names
                    team1_elem = await item.query_selector('.match-item__opponent:nth-child(1) .match-item__opponent-name')
                    team2_elem = await item.query_selector('.match-item__opponent:nth-child(3) .match-item__opponent-name')
                    
                    if team1_elem:
                        match_data['team1'] = (await team1_elem.inner_text()).strip()
                    if team2_elem:
                        match_data['team2'] = (await team2_elem.inner_text()).strip()
                    
                    # Get scores
                    score1_elem = await item.query_selector('.match-item__opponent-score-first')
                    score2_elem = await item.query_selector('.match-item__opponent-score-second')
                    
                    if score1_elem:
                        score1 = (await score1_elem.inner_text()).strip()
                        if score1 and score1 != '-':
                            match_data['score1'] = int(score1)
                    
                    if score2_elem:
                        score2 = (await score2_elem.inner_text()).strip()
                        if score2 and score2 != '-':
                            match_data['score2'] = int(score2)
                    
                    # Get rounds won (for live matches)
                    round_elems = await item.query_selector_all('.match-item__opponent-round')
                    if len(round_elems) >= 2:
                        r1 = (await round_elems[0].inner_text()).strip()
                        r2 = (await round_elems[1].inner_text()).strip()
                        if r1:
                            match_data['mapsWonTeam1'] = int(r1)
                        if r2:
                            match_data['mapsWonTeam2'] = int(r2)
                    
                    # Get status (live/upcoming/completed)
                    live_elem = await item.query_selector('.live')
                    if live_elem:
                        match_data['status'] = 'live'
                    elif 'score1' in match_data or 'score2' in match_data:
                        match_data['status'] = 'completed'
                    else:
                        match_data['status'] = 'upcoming'
                    
                    # Get tournament info
                    tournament_elem = await item.query_selector('.nv-live-meta')
                    if tournament_elem:
                        tournament_text = (await tournament_elem.inner_text()).strip()
                        match_data['tournamentInfo'] = tournament_text
                    
                    # Get stage
                    stage_elem = await item.query_selector('.match-item__league-stage')
                    if stage_elem:
                        stage = (await stage_elem.inner_text()).strip()
                        match_data['stage'] = stage
                    
                    # Get team logos
                    team1_logo_elem = await item.query_selector('.match-item__opponent:nth-child(1) img')
                    team2_logo_elem = await item.query_selector('.match-item__opponent:nth-child(3) img')
                    
                    if team1_logo_elem:
                        match_data['team1Logo'] = await team1_logo_elem.get_attribute('src')
                    if team2_logo_elem:
                        match_data['team2Logo'] = await team2_logo_elem.get_attribute('src')
                    
                    # Only add if we have team names
                    if 'team1' in match_data and 'team2' in match_data:
                        matches.append(match_data)
                        
                except Exception:
                    continue
            
            # Get tournament info from JSON-LD
            scripts = await page.query_selector_all('script[type="application/ld+json"]')
            tournament_info = {}
            
            for script in scripts:
                content = await script.inner_text()
                if content.strip():
                    try:
                        data = json.loads(content)
                        if data.get('@type') == 'SportsEvent':
                            tournament_info = {
                                'name': data.get('name'),
                                'sport': data.get('sport'),
                                'startDate': data.get('startDate'),
                                'endDate': data.get('endDate')
                            }
                            break
                    except json.JSONDecodeError:
                        continue
            
            return {
                "success": True,
                "data": {
                    "tournament": tournament_info,
                    "matches": matches,
                    "totalMatches": len(matches)
                }
            }
            
        finally:
            await browser.close()