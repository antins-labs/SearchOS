"""
SNK Corporation KOF XIV Access Skill

Fetches character, team, and story data from the official SNK KOF XIV website.
The site uses JavaScript for dynamic content loading, so Playwright is required.
"""

import asyncio
import re
from typing import Any
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = "https://www.snk-corp.co.jp/us/games/kof-xiv"

# Known character URLs (extracted from team pages)
CHARACTER_URLS = {
    "kusanagi": "/us/games/kof-xiv/characters/kusanagi.php",
    "benimaru": "/us/games/kof-xiv/characters/benimaru.php",
    "daimon": "/us/games/kof-xiv/characters/daimon.php",
    "antonov": "/us/games/kof-xiv/characters/antonov.php",
    "verse": "/us/games/kof-xiv/characters/verse.php",
}

# Known team URLs
TEAM_URLS = {
    "japan": {"name": "JAPAN TEAM", "url": "/us/games/kof-xiv/teams/japan.php"},
    "officialinvi": {"name": "OFFICIAL INVITATION TEAM", "url": "/us/games/kof-xiv/teams/officialinvi.php"},
    "southamerica": {"name": "SOUTH AMERICA TEAM", "url": "/us/games/kof-xiv/teams/southamerica.php"},
    "yagami": {"name": "YAGAMI TEAM", "url": "/us/games/kof-xiv/teams/yagami.php"},
    "kim": {"name": "KIM TEAM", "url": "/us/games/kof-xiv/teams/kim.php"},
    "mexico": {"name": "MEXICO TEAM", "url": "/us/games/kof-xiv/teams/mexico.php"},
    "another": {"name": "ANOTHER WORLD TEAM", "url": "/us/games/kof-xiv/teams/another.php"},
    "villains": {"name": "VILLAINS TEAM", "url": "/us/games/kof-xiv/teams/villains.php"},
    "china": {"name": "CHINA TEAM", "url": "/us/games/kof-xiv/teams/china.php"},
    "kdash": {"name": "K' TEAM", "url": "/us/games/kof-xiv/teams/kdash.php"},
    "ikari": {"name": "IKARI TEAM", "url": "/us/games/kof-xiv/teams/ikari.php"},
    "southtown": {"name": "SOUTH TOWN TEAM", "url": "/us/games/kof-xiv/teams/southtown.php"},
    "fatalfury": {"name": "FATAL FURY TEAM", "url": "/us/games/kof-xiv/teams/fatalfury.php"},
    "women": {"name": "WOMEN FIGHTERS TEAM", "url": "/us/games/kof-xiv/teams/women.php"},
    "psychosoldier": {"name": "PSYCHO SOLDIER TEAM", "url": "/us/games/kof-xiv/teams/psychosoldier.php"},
    "artoffighting": {"name": "ART OF FIGHTING TEAM", "url": "/us/games/kof-xiv/teams/artoffighting.php"},
}


async def fetch_with_browser(url: str, timeout: int = 12000, wait_time: float = 1.5):
    """Fetch page content using Playwright browser automation."""
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    try:
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US"
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            await asyncio.sleep(wait_time)
            
            content = await page.content()
            body_text = await page.locator("body").inner_text()
            title = await page.title()
            
            return {
                "success": True,
                "url": url,
                "title": title,
                "content": content,
                "text": body_text,
                "content_length": len(content),
                "page": page,
                "context": context,
                "browser": browser,
                "playwright": p,
            }
        except PlaywrightTimeoutError:
            try:
                content = await page.content()
                body_text = await page.locator("body").inner_text()
                return {
                    "success": True,
                    "url": url,
                    "partial": True,
                    "content": content,
                    "text": body_text,
                    "content_length": len(content),
                    "warning": "Page load timed out, content may be incomplete",
                    "page": page,
                    "context": context,
                    "browser": browser,
                    "playwright": p,
                }
            except:
                await browser.close()
                await p.stop()
                return {
                    "success": False,
                    "error": "Page load timed out and no content available",
                    "url": url
                }
        except Exception as e:
            await browser.close()
            await p.stop()
            return {
                "success": False,
                "error": f"Page load error: {str(e)}",
                "url": url
            }
    except Exception as e:
        try:
            await browser.close()
        except:
            pass
        try:
            await p.stop()
        except:
            pass
        return {
            "success": False,
            "error": f"Browser error: {str(e)}",
            "url": url
        }


async def cleanup_browser(result: dict):
    """Clean up browser resources."""
    if "browser" in result:
        try:
            await result["browser"].close()
        except:
            pass
    if "playwright" in result:
        try:
            await result["playwright"].stop()
        except:
            pass
    for key in ["page", "context", "browser", "playwright"]:
        if key in result:
            del result[key]


def parse_character_profile(text: str) -> dict[str, str]:
    """Parse character profile from page text."""
    profile = {}
    
    # Extract voice actor (CV)
    cv_match = re.search(r'（\s*CV\s*:\s*([^）]+)\s*）', text)
    if cv_match:
        profile['CV'] = cv_match.group(1).strip()
    
    # Extract profile fields (format: "Field\n:Value" or "Field:Value")
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Check for "Field\n:Value" pattern
        if line and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if next_line.startswith(':'):
                value = next_line[1:].strip()
                field = line.replace(':', '').strip()
                if field and value and field not in ['（ CV']:
                    profile[field] = value
                i += 2
                continue
        
        # Check for "Field:Value" pattern
        if ':' in line and len(line) < 100:
            parts = line.split(':', 1)
            if len(parts) == 2:
                field = parts[0].strip()
                value = parts[1].strip()
                if field and value and len(field) < 50 and field not in ['（ CV']:
                    profile[field] = value
        
        i += 1
    
    return profile


async def get_character(params: dict[str, Any]) -> dict[str, Any]:
    """Get character profile information."""
    character_name = params.get("character", "").lower().strip()
    
    if not character_name:
        return {
            "success": False,
            "error": "Missing required parameter: character",
            "available_characters": list(CHARACTER_URLS.keys())
        }
    
    # Find character URL
    char_url = None
    for name, url in CHARACTER_URLS.items():
        if character_name in name or name in character_name:
            char_url = url
            break
    
    if not char_url:
        char_url = f"/us/games/kof-xiv/characters/{character_name}.php"
    
    full_url = f"https://www.snk-corp.co.jp{char_url}"
    
    result = await fetch_with_browser(full_url)
    
    if result.get("success"):
        text = result.get("text", "")
        profile = parse_character_profile(text)
        
        result["character"] = character_name
        result["profile"] = profile
        await cleanup_browser(result)
    
    return result


async def get_team(params: dict[str, Any]) -> dict[str, Any]:
    """Get team information including members."""
    team_name = params.get("team", "").lower().strip()
    
    if not team_name:
        return {
            "success": False,
            "error": "Missing required parameter: team",
            "available_teams": list(TEAM_URLS.keys())
        }
    
    # Find team URL
    team_info = None
    for name, info in TEAM_URLS.items():
        if team_name in name or name in team_name:
            team_info = info
            break
    
    if not team_info:
        team_info = {
            "name": team_name.upper(),
            "url": f"/us/games/kof-xiv/teams/{team_name}.php"
        }
    
    full_url = f"https://www.snk-corp.co.jp{team_info['url']}"
    
    result = await fetch_with_browser(full_url)
    
    if result.get("success"):
        page = result.get("page")
        
        if page:
            try:
                # Get character links from team page
                char_links = await page.locator('a[href*="/characters/"][href$=".php"]').all()
                members = []
                seen = set()
                for link in char_links:
                    href = await link.get_attribute('href')
                    if href and href not in seen:
                        name = href.split('/')[-1].replace('.php', '')
                        try:
                            link_text = await link.inner_text()
                            display_name = link_text.strip() if link_text.strip() else name.title()
                        except:
                            display_name = name.title()
                        
                        members.append({
                            "name": display_name,
                            "id": name,
                            "url": f"https://www.snk-corp.co.jp{href}"
                        })
                        seen.add(href)
                
                result["team"] = team_info.get("name", team_name)
                result["members"] = members
            except Exception as e:
                result["team"] = team_info.get("name", team_name)
                result["members"] = []
            finally:
                await cleanup_browser(result)
        else:
            result["team"] = team_info.get("name", team_name)
            result["members"] = []
    
    return result


async def list_teams(params: dict[str, Any]) -> dict[str, Any]:
    """List all available teams."""
    # Return known teams directly (faster than fetching)
    teams = [
        {"name": info["name"], "id": tid, "url": f"https://www.snk-corp.co.jp{info['url']}"}
        for tid, info in TEAM_URLS.items()
    ]
    
    return {
        "success": True,
        "url": f"{BASE_URL}/teams/",
        "teams": teams,
        "total": len(teams)
    }


async def get_story(params: dict[str, Any]) -> dict[str, Any]:
    """Get story information."""
    full_url = f"{BASE_URL}/story/"
    
    result = await fetch_with_browser(full_url)
    
    if result.get("success"):
        result["story_url"] = full_url
        await cleanup_browser(result)
    
    return result


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Main entry point for the SNK KOF XIV skill.
    
    Dispatches to the appropriate function based on params["function"].
    """
    function = params.get("function", "")
    
    if function == "get_character":
        return await get_character(params)
    elif function == "get_team":
        return await get_team(params)
    elif function == "list_teams":
        return await list_teams(params)
    elif function == "get_story":
        return await get_story(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_character", "get_team", "list_teams", "get_story"]
        }