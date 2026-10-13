"""
Noff.gg Clash Royale Card Stats Access Skill

Fetches card statistics from noff.gg/clash-royale/card/{card_name}
Handles both single-entity and multi-entity cards (e.g., Rascals with Boy and Girl entities).
"""

from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import async_playwright


async def _fetch_card(card_name: str) -> dict[str, Any]:
    """
    Fetch card data from noff.gg
    
    Args:
        card_name: URL-friendly card name (e.g., 'mega-knight', 'rascals')
    
    Returns:
        Card data dictionary with name, rarity, type, stats, etc.
    """
    url = f"https://www.noff.gg/clash-royale/card/{card_name}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)  # Wait for JS rendering
            
            # Check if page loaded correctly
            title = await page.title()
            if 'Clash Royale' not in title and '404' in title:
                return {
                    'error': 'Card not found',
                    'card_name': card_name,
                    'url': url
                }
            
            # Extract card data
            card_data = await page.evaluate('''() => {
                const data = { url: window.location.href };
                const bodyText = document.body.innerText;
                
                // Card name
                const h1 = document.querySelector('h1');
                if (h1) data.name = h1.innerText.trim();
                
                // Rarity
                const rarityMatch = bodyText.match(/Rarity\\n([A-Za-z]+)/);
                if (rarityMatch) data.rarity = rarityMatch[1];
                
                // Type
                const typeMatch = bodyText.match(/Type\\n([A-Za-z]+)/);
                if (typeMatch) data.type = typeMatch[1];
                
                // Arena
                const arenaMatch = bodyText.match(/Arena (\\d+)/);
                if (arenaMatch) data.arena = parseInt(arenaMatch[1]);
                
                // Description (flavor text)
                const descMatch = bodyText.match(/Arena \\d+\\n\\n([\\s\\S]+?)\\n\\nLevel/);
                if (descMatch) data.description = descMatch[1].trim();
                
                // Level (base stats level)
                const levelMatch = bodyText.match(/Level (\\d+)/);
                if (levelMatch) data.level = parseInt(levelMatch[1]);
                
                // Check for multi-entity cards (like Rascals, Goblin Barrel)
                const entityContainers = document.querySelectorAll('.stats-container[data-key]');
                
                if (entityContainers.length > 0) {
                    // Multi-entity card
                    const entities = {};
                    
                    entityContainers.forEach(container => {
                        const entityKey = container.getAttribute('data-key');
                        // Convert snake_case to Title Case
                        const entityName = entityKey
                            .replace(/_/g, ' ')
                            .replace(/\\b\\w/g, l => l.toUpperCase());
                        
                        const stats = {};
                        container.querySelectorAll('.stat').forEach(stat => {
                            const nameEl = stat.querySelector('.stat-name');
                            const valueEl = stat.querySelector('.stat-value');
                            if (nameEl && valueEl) {
                                stats[nameEl.innerText.trim()] = valueEl.innerText.trim();
                            }
                        });
                        
                        if (Object.keys(stats).length > 0) {
                            entities[entityName] = stats;
                        }
                    });
                    
                    // Get entity counts (e.g., "x2" for Rascal Girls)
                    document.querySelectorAll('.stat').forEach(stat => {
                        const text = stat.innerText;
                        if (text.includes('Count')) {
                            const lines = text.split('\\n');
                            if (lines.length >= 2) {
                                const entityMatch = lines[0].match(/(.+) Count/);
                                const countMatch = lines[1].match(/x(\\d+)/);
                                if (entityMatch && countMatch) {
                                    const entityName = entityMatch[1].trim();
                                    if (entities[entityName]) {
                                        entities[entityName].count = parseInt(countMatch[1]);
                                    }
                                }
                            }
                        }
                    });
                    
                    if (Object.keys(entities).length > 0) {
                        data.entities = entities;
                    }
                } else {
                    // Single-entity card
                    const stats = {};
                    document.querySelectorAll('.stat').forEach(stat => {
                        const nameEl = stat.querySelector('.stat-name');
                        const valueEl = stat.querySelector('.stat-value');
                        if (nameEl && valueEl) {
                            stats[nameEl.innerText.trim()] = valueEl.innerText.trim();
                        }
                    });
                    if (Object.keys(stats).length > 0) {
                        data.stats = stats;
                    }
                }
                
                // Battle Trends
                const winRateMatch = bodyText.match(/Win Rate \\(([\\d.]+)%\\)/);
                if (winRateMatch) data.winRate = winRateMatch[1] + '%';
                
                const pickRateMatch = bodyText.match(/Pick Rate \\(([\\d.]+)%\\)/);
                if (pickRateMatch) data.pickRate = pickRateMatch[1] + '%';
                
                const trendMatch = bodyText.match(/has been (below average|above average) in the last 30 days/);
                if (trendMatch) data.trend = trendMatch[1];
                
                return data;
            }''')
            
            # Validate we got meaningful data
            if not card_data.get('name'):
                return {
                    'error': 'Could not extract card data',
                    'card_name': card_name,
                    'url': url
                }
            
            return card_data
            
        except asyncio.TimeoutError:
            return {
                'error': 'Page load timeout',
                'card_name': card_name,
                'url': url
            }
        except Exception as e:
            return {
                'error': str(e),
                'card_name': card_name,
                'url': url
            }
        finally:
            await browser.close()


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the noff.gg access skill.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dictionary with requested data or error information
    """
    function = params.get('function', '')
    
    if function == 'get_card':
        card_name = params.get('card_name', '')
        if not card_name:
            return {'error': 'Missing required parameter: card_name'}
        
        # Normalize card name to URL format
        card_name = card_name.lower().strip().replace(' ', '-')
        
        result = await _fetch_card(card_name)
        return result
    
    else:
        return {
            'error': f'Unknown function: {function}',
            'available_functions': ['get_card']
        }