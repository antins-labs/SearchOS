"""
LPL (League of Legends Pro League) Data Access Skill

This skill fetches data from lpl.qq.com including:
- Season/tournament information (EventdataTab)
- Team list and details
- Rank data (team, player, hero statistics) - when available
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
import aiohttp
from playwright.async_api import async_playwright


async def execute(params: Dict[str, Any], ctx=None) -> Dict[str, Any]:
    """
    Execute LPL data retrieval
    
    Args:
        params: Dictionary containing:
            - function: The function to call
            - Other parameters depending on function

    
    Returns:
        Dictionary with results or error
    """
    function = params.get("function", "")
    
    if function == "get_seasons":
        return await get_seasons()
    elif function == "get_teams":
        return await get_teams()
    elif function == "get_team_detail":
        team_id = params.get("team_id")
        if not team_id:
            return {"error": "Missing required parameter: team_id"}
        return await get_team_detail(team_id)
    elif function == "get_rank_data":
        season_id = params.get("season_id", "237")
        data_type = params.get("data_type", "player")  # team, player, hero
        return await get_rank_data(season_id, data_type, params.get("stage_ids"))
    elif function == "get_rank_page_content":
        season_id = params.get("season_id", "237")
        return await get_rank_page_content(season_id, params.get("stage_ids"))
    else:
        return {"error": f"Unknown function: {function}"}


async def fetch_js_data(url: str, var_name: str = None) -> Dict[str, Any]:
    """Fetch and parse JavaScript data file"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://lpl.qq.com/',
        'Accept': '*/*',
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=15) as resp:
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}"}
                
                content_bytes = await resp.read()
                
                # Try different encodings
                for encoding in ['utf-8', 'gbk', 'gb2312']:
                    try:
                        content = content_bytes.decode(encoding)
                        break
                    except:
                        continue
                else:
                    content = content_bytes.decode('utf-8', errors='ignore')
                
                # Extract JSON from JS variable
                if var_name and f'var {var_name}=' in content:
                    json_str = content.split(f'var {var_name}=')[1].split(';')[0].strip()
                    return json.loads(json_str)
                elif var_name and f'return [' in content:
                    # Handle function-wrapped arrays
                    start = content.find('return [') + 7
                    end = content.rfind(']') + 1
                    json_str = content[start:end]
                    return json.loads(json_str)
                elif content.strip().startswith('['):
                    return json.loads(content)
                elif content.strip().startswith('{'):
                    return json.loads(content)
                else:
                    return {"error": "Could not parse JavaScript data", "preview": content[:500]}
                    
        except asyncio.TimeoutError:
            return {"error": "Request timeout"}
        except json.JSONDecodeError as e:
            return {"error": f"JSON parse error: {e}"}
        except Exception as e:
            return {"error": str(e)}


async def get_seasons() -> Dict[str, Any]:
    """Get all available seasons and tournaments"""
    url = "https://lol.qq.com/act/AutoCMS/publish/LOLWeb/EventdataTab/EventdataTab.js"
    
    result = await fetch_js_data(url, "EventdataTab")
    
    if "error" in result:
        return result
    
    # Process the data
    seasons = []
    for season in result:
        season_info = {
            "name": season.get("name", ""),
            "domestic": [],
            "abroad": []
        }
        
        for event in season.get("domestic", []):
            season_info["domestic"].append({
                "name": event.get("gameName", ""),
                "game_id": event.get("iGameId", ""),
                "stage_ids": event.get("sGameType", ""),
                "url": event.get("url", "")
            })
        
        for event in season.get("abroad", []):
            season_info["abroad"].append({
                "name": event.get("gameName", ""),
                "game_id": event.get("iGameId", ""),
                "stage_ids": event.get("sGameType", ""),
                "url": event.get("url", "")
            })
        
        seasons.append(season_info)
    
    return {
        "success": True,
        "seasons": seasons,
        "total": len(seasons)
    }


async def get_teams() -> Dict[str, Any]:
    """Get all teams list"""
    url = "https://lpl.qq.com/web201612/data/LOL_MATCH2_TEAM_LIST.js"
    
    result = await fetch_js_data(url, "TeamList")
    
    if "error" in result:
        return result
    
    if result.get("status") != "0":
        return {"error": "Team list API returned error status"}
    
    teams = []
    msg = result.get("msg", {})
    
    for team_id, team_data in msg.items():
        teams.append({
            "team_id": team_data.get("TeamId", team_id),
            "name": team_data.get("TeamName", ""),
            "short_name": team_data.get("TeamShortName", ""),
            "en_name": team_data.get("TeamEnName", ""),
            "logo": team_data.get("TeamLogo", ""),
            "logo_deep": team_data.get("TeamLogoDeep", ""),
            "url": team_data.get("sUrl", ""),
            "place": team_data.get("Place", "")
        })
    
    # Sort by team_id
    teams.sort(key=lambda x: int(x["team_id"]) if x["team_id"].isdigit() else 0)
    
    return {
        "success": True,
        "teams": teams,
        "total": len(teams)
    }


async def get_team_detail(team_id: str) -> Dict[str, Any]:
    """Get team detail page content"""
    url = f"https://lpl.qq.com/web202301/team-detail.html?tid={team_id}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-CN',
                timezone_id='Asia/Shanghai'
            )
            
            page = await context.new_page()
            
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Extract team info from page
            team_info = await page.evaluate('''() => {
                const info = {};
                
                // Team name
                const nameEl = document.querySelector('.team-name');
                if (nameEl) info.name = nameEl.innerText.trim();
                
                // Team logo
                const logoEl = document.querySelector('.team-logo img, .team-img img, .team-banner img');
                if (logoEl) info.logo = logoEl.src;
                
                // Team description
                const descEl = document.querySelector('.team-desc, .team-intro, [class*="desc"]');
                if (descEl) info.description = descEl.innerText.trim();
                
                // Team stats from the stats section
                const statsSection = document.querySelector('.team-data, .team-stats, [class*="stats"]');
                info.stats = {};
                if (statsSection) {
                    const statItems = statsSection.querySelectorAll('[class*="stat"], .data-item');
                    statItems.forEach(item => {
                        const label = item.querySelector('.label, .name, [class*="label"]');
                        const value = item.querySelector('.value, .num, [class*="value"]');
                        if (label && value) {
                            info.stats[label.innerText.trim()] = value.innerText.trim();
                        }
                    });
                }
                
                // Try to extract stats from common patterns
                const statLabels = document.querySelectorAll('.team-data-item, .stat-item, [class*="data-item"]');
                if (statLabels.length > 0) {
                    statLabels.forEach(item => {
                        const text = item.innerText.trim();
                        const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                        if (lines.length >= 2) {
                            info.stats[lines[0]] = lines[1];
                        }
                    });
                }
                
                // Players - look for player list
                info.players = [];
                const playerEls = document.querySelectorAll('.player-name');
                playerEls.forEach(el => {
                    const name = el.innerText.trim();
                    if (name && name.length > 0 && name.length < 20) {
                        info.players.push({"name": name});
                    }
                });
                
                // If no players found with .player-name, try other selectors
                if (info.players.length === 0) {
                    const altPlayerEls = document.querySelectorAll('[class*="player"] .name, .roster .name');
                    altPlayerEls.forEach(el => {
                        const name = el.innerText.trim();
                        if (name && name.length > 0 && name.length < 20) {
                            info.players.push({"name": name});
                        }
                    });
                }
                
                return info;
            }''')
            
            team_info["url"] = url
            team_info["team_id"] = team_id
            
            return {
                "success": True,
                "team": team_info
            }
            
        except Exception as e:
            return {"error": str(e)}
        finally:
            await browser.close()


async def get_rank_data(season_id: str, data_type: str = "player", stage_ids: str = None) -> Dict[str, Any]:
    """
    Get rank data for a specific season
    Note: The API endpoints may not be directly accessible, so this function
    attempts to fetch data but may return empty results if the API is blocked.
    """
    base_url = "https://lpl.qq.com/compound/public"
    endpoint = f"{base_url}/{data_type}"
    
    params = {"seasonId": season_id}
    if stage_ids:
        params["stageIds"] = stage_ids
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://lpl.qq.com/web202301/rank.html',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(endpoint, params=params, headers=headers, timeout=15) as resp:
                if resp.status == 404:
                    return {
                        "error": "Rank API endpoint not accessible (404). The data may require browser rendering or authentication.",
                        "endpoint": endpoint,
                        "params": params,
                        "alternative": "Use get_rank_page_content function to extract rendered page data"
                    }
                
                if resp.status != 200:
                    return {"error": f"HTTP {resp.status}"}
                
                content_bytes = await resp.read()
                content = content_bytes.decode('utf-8', errors='ignore')
                
                try:
                    data = json.loads(content)
                    return {
                        "success": True,
                        "data_type": data_type,
                        "season_id": season_id,
                        "data": data.get("data", data),
                        "total": len(data.get("data", [])) if isinstance(data.get("data"), list) else 1
                    }
                except json.JSONDecodeError:
                    return {"error": "Response is not valid JSON", "preview": content[:500]}
                    
        except asyncio.TimeoutError:
            return {"error": "Request timeout"}
        except Exception as e:
            return {"error": str(e)}


async def get_rank_page_content(season_id: str = "237", stage_ids: str = None) -> Dict[str, Any]:
    """
    Get rank page content by rendering the page in browser
    This extracts visible content from the rank page
    """
    url = f"https://lpl.qq.com/web202301/rank.html?seasonId={season_id}"
    if stage_ids:
        url += f"&stageIds={stage_ids}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-CN',
                timezone_id='Asia/Shanghai'
            )
            
            page = await context.new_page()
            
            # Track network requests
            api_requests = []
            
            def log_request(request):
                if 'compound' in request.url or 'rank' in request.url.lower():
                    api_requests.append(request.url)
            
            page.on('request', log_request)
            
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Get page title
            title = await page.title()
            
            # Extract page configuration
            page_config = await page.evaluate('''() => {
                const rd = window.rankData || {};
                const ed = window.EventdataTab || [];
                
                return {
                    currentTab: rd.currentTab,
                    searchSeasonId: rd.searchSeasonId,
                    searchStageIds: rd.searchStageIds,
                    currentSort: rd.currentSort,
                    top3: rd.top3,
                    eventdataCount: ed.length
                };
            }''')
            
            # Extract available tabs
            tabs = await page.evaluate('''() => {
                const tabEls = document.querySelectorAll('[data-tab]');
                const seen = new Set();
                return Array.from(tabEls)
                    .map(el => ({
                        type: el.getAttribute('data-tab'),
                        text: el.innerText.trim()
                    }))
                    .filter(t => t.text && !seen.has(t.type + t.text) && (seen.add(t.type + t.text) || true));
            }''')
            
            # Extract table headers for each tab
            headers = await page.evaluate('''() => {
                const result = {
                    team: [],
                    player: [],
                    hero: []
                };
                
                // Team headers
                const teamHeaders = document.querySelectorAll('#rank-team-swiper .rank-tabl-head span');
                result.team = Array.from(teamHeaders).map(h => h.innerText.trim()).filter(t => t);
                
                // Player headers
                const playerHeaders = document.querySelectorAll('#rank-player-swiper .rank-tabl-head span');
                result.player = Array.from(playerHeaders).map(h => h.innerText.trim()).filter(t => t);
                
                // Hero headers
                const heroHeaders = document.querySelectorAll('#rank-hero-swiper .rank-tabl-head span');
                result.hero = Array.from(heroHeaders).map(h => h.innerText.trim()).filter(t => t);
                
                return result;
            }''')
            
            # Try to extract any visible data
            visible_data = await page.evaluate('''() => {
                const result = {
                    team: [],
                    player: [],
                    hero: []
                };
                
                // Team data
                const teamRows = document.querySelectorAll('#rank-team-swiper .rank-tabl-body li');
                teamRows.forEach((row, idx) => {
                    if (idx < 20) {  // Limit to first 20
                        const cells = row.querySelectorAll('span');
                        const rowData = Array.from(cells).map(c => c.innerText.trim());
                        if (rowData.length > 0 && rowData.some(d => d)) {
                            result.team.push(rowData);
                        }
                    }
                });
                
                // Player data
                const playerRows = document.querySelectorAll('#rank-player-swiper .rank-tabl-body li');
                playerRows.forEach((row, idx) => {
                    if (idx < 20) {
                        const cells = row.querySelectorAll('span');
                        const rowData = Array.from(cells).map(c => c.innerText.trim());
                        if (rowData.length > 0 && rowData.some(d => d)) {
                            result.player.push(rowData);
                        }
                    }
                });
                
                // Hero data
                const heroRows = document.querySelectorAll('#rank-hero-swiper .rank-tabl-body li');
                heroRows.forEach((row, idx) => {
                    if (idx < 20) {
                        const cells = row.querySelectorAll('span');
                        const rowData = Array.from(cells).map(c => c.innerText.trim());
                        if (rowData.length > 0 && rowData.some(d => d)) {
                            result.hero.push(rowData);
                        }
                    }
                });
                
                return result;
            }''')
            
            return {
                "success": True,
                "url": url,
                "title": title,
                "page_config": page_config,
                "tabs": tabs,
                "headers": headers,
                "data": visible_data,
                "api_requests_detected": api_requests,
                "note": "Data tables may be empty if the API is not accessible. Use get_seasons and get_teams for reliable data."
            }
            
        except Exception as e:
            return {"error": str(e)}
        finally:
            await browser.close()


if __name__ == "__main__":
    # Test the functions
    import sys
    
    async def test():
        print("Testing get_seasons...")
        result = await get_seasons()
        print(f"Success: {result.get('success')}, Total seasons: {result.get('total', 0)}")
        
        print("\nTesting get_teams...")
        result = await get_teams()
        print(f"Success: {result.get('success')}, Total teams: {result.get('total', 0)}")
        if result.get('teams'):
            print(f"First team: {result['teams'][0]}")
        
        print("\nTesting get_team_detail...")
        result = await get_team_detail("1")
        print(f"Success: {result.get('success')}")
        if result.get('team'):
            print(f"Team: {result['team'].get('name', 'N/A')}")
            print(f"Players: {len(result['team'].get('players', []))}")
        
        print("\nTesting get_rank_page_content...")
        result = await get_rank_page_content("237")
        print(f"Success: {result.get('success')}")
        print(f"Title: {result.get('title')}")
        print(f"Tabs: {result.get('tabs')}")
    
    asyncio.run(test())