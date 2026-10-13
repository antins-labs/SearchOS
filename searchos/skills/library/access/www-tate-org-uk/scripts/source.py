"""
SearchOS Access Skill for Tate Turner Prize
Extracts Turner Prize winners, nominees, and bursary recipients from tate.org.uk
"""

import asyncio
import re
from typing import Any, Dict, List, Optional


async def execute(params: Dict[str, Any], ctx=None) -> Dict[str, Any]:
    """
    Execute Turner Prize data extraction.
    
    Functions:
    - get_turner_prize_years: Get all Turner Prize years with nominees and winners
    - get_winners_grid: Get the visual winners grid with artist details
    - get_bursary_recipients: Get 2020 Turner Bursary recipients
    - get_year_details: Get details for a specific year
    """
    function = params.get("function", "")
    
    if function == "get_turner_prize_years":
        return await get_turner_prize_years(params)
    elif function == "get_winners_grid":
        return await get_winners_grid(params)
    elif function == "get_bursary_recipients":
        return await get_bursary_recipients(params)
    elif function == "get_year_details":
        return await get_year_details(params)
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": [
                "get_turner_prize_years",
                "get_winners_grid",
                "get_bursary_recipients",
                "get_year_details"
            ]
        }


async def get_turner_prize_years(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get all Turner Prize years with nominees and winners.
    
    Optional params:
    - start_year: Filter from this year (default: 1984)
    - end_year: Filter to this year (default: current year)
    """
    start_year = params.get("start_year", 1984)
    end_year = params.get("end_year", 2025)
    
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Navigate to Turner Prize page
            try:
                await page.goto('https://www.tate.org.uk/art/turner-prize', timeout=45000)
            except:
                pass  # Continue even if timeout
            
            await asyncio.sleep(5)
            
            # Extract year sections with complete information
            year_data = await page.evaluate('''
                () => {
                    const results = [];
                    const h3s = document.querySelectorAll('h3');
                    
                    h3s.forEach(h3 => {
                        const yearText = h3.innerText.trim();
                        if (/^\\d{4}$/.test(yearText) && parseInt(yearText) >= 1984 && parseInt(yearText) <= 2025) {
                            const year = yearText;
                            
                            // Get all siblings until next h3
                            let content = [];
                            let sibling = h3.nextElementSibling;
                            
                            while (sibling && sibling.tagName !== 'H3') {
                                if (sibling.innerText && sibling.innerText.trim()) {
                                    content.push({
                                        tag: sibling.tagName,
                                        text: sibling.innerText.trim(),
                                        html: sibling.outerHTML
                                    });
                                }
                                sibling = sibling.nextElementSibling;
                            }
                            
                            results.push({
                                year: year,
                                content: content
                            });
                        }
                    });
                    
                    return results;
                }
            ''')
            
            # Parse the data
            parsed_data = []
            for yd in year_data:
                year = int(yd['year'])
                
                # Filter by year range
                if year < start_year or year > end_year:
                    continue
                
                content = yd['content']
                
                shortlisted = []
                winner = None
                notes = ''
                
                # Parse content
                for i, item in enumerate(content):
                    text = item['text']
                    
                    # Check for shortlisted list
                    if 'shortlisted' in text.lower():
                        # Next item should be a UL with artists
                        if i + 1 < len(content) and content[i + 1]['tag'] == 'UL':
                            # Parse list items from HTML
                            li_matches = re.findall(r'<li[^>]*>(.*?)</li>', content[i + 1]['html'], re.DOTALL)
                            for match in li_matches:
                                # Clean HTML tags
                                artist = re.sub(r'<[^>]+>', '', match).strip()
                                if artist:
                                    shortlisted.append(artist)
                    
                    # Check for winner
                    if 'winner' in text.lower():
                        winner_match = re.search(r'Winner:\\s*(.+)', text, re.IGNORECASE)
                        if winner_match:
                            winner = winner_match.group(1).strip()
                    
                    # Check for special notes
                    if any(keyword in text.lower() for keyword in ['cancelled', 'bursary', 'not awarded', 'no prize']):
                        notes = text
                
                parsed_data.append({
                    'year': year,
                    'winner': winner,
                    'shortlisted': shortlisted,
                    'notes': notes
                })
            
            return {
                'success': True,
                'data': {
                    'years': parsed_data,
                    'total_years': len(parsed_data),
                    'years_with_nominees': len([y for y in parsed_data if y['shortlisted']]),
                    'source': 'https://www.tate.org.uk/art/turner-prize'
                }
            }
            
        finally:
            await browser.close()


async def get_winners_grid(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the visual winners grid with artist details and URLs.
    This shows past winners with links to their artist pages.
    """
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Navigate to Turner Prize page
            try:
                await page.goto('https://www.tate.org.uk/art/turner-prize', timeout=45000)
            except:
                pass
            
            await page.wait_for_selector('.card--artist', timeout=20000)
            await asyncio.sleep(3)
            
            # Extract winners grid
            winners_grid = await page.evaluate('''
                () => {
                    const cards = document.querySelectorAll('.card--artist');
                    const winners = [];
                    
                    cards.forEach((card, idx) => {
                        const link = card.querySelector('a[href*="/art/artists/"]');
                        const text = card.innerText || '';
                        
                        if (link) {
                            const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
                            const name = lines[1] || lines[0] || 'Unknown';
                            
                            // Extract birth year if available
                            let birthYear = null;
                            const yearMatch = text.match(/born\\s+(\\d{4})/i);
                            if (yearMatch) {
                                birthYear = yearMatch[1];
                            }
                            
                            winners.push({
                                index: idx + 1,
                                name: name,
                                birth_year: birthYear,
                                url: link.href,
                                full_text: text
                            });
                        }
                    });
                    
                    return winners;
                }
            ''')
            
            return {
                'success': True,
                'data': {
                    'winners': winners_grid,
                    'total': len(winners_grid),
                    'source': 'https://www.tate.org.uk/art/turner-prize'
                }
            }
            
        finally:
            await browser.close()


async def get_bursary_recipients(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get the 2020 Turner Bursary recipients.
    These were awarded instead of the Turner Prize in 2020 due to COVID-19.
    """
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Navigate to bursaries page
            try:
                await page.goto('https://www.tate.org.uk/art/turner-prize/turner-bursaries', timeout=45000)
            except:
                pass
            
            await asyncio.sleep(5)
            
            # Extract bursary recipients
            bursary_data = await page.evaluate('''
                () => {
                    const recipients = [];
                    
                    // Find all h3 headings (artist names)
                    const h3s = document.querySelectorAll('h3');
                    
                    h3s.forEach(h3 => {
                        const name = h3.innerText.trim();
                        
                        // Filter out navigation and other non-artist headings
                        if (name && name.length > 0 && name.length < 50 && 
                            !name.toLowerCase().includes('menu') &&
                            !name.toLowerCase().includes('skip') &&
                            !name.toLowerCase().includes('turner bursaries') &&
                            !name.toLowerCase().includes('sign') &&
                            !name.toLowerCase().includes('about') &&
                            !name.toLowerCase().includes('support') &&
                            !name.toLowerCase().includes('join') &&
                            !name.toLowerCase().includes('we recommend') &&
                            !name.toLowerCase().includes('jury')) {
                            
                            // Get description from next paragraph
                            let description = '';
                            let sibling = h3.nextElementSibling;
                            let count = 0;
                            
                            while (sibling && count < 5) {
                                if (sibling.tagName === 'P') {
                                    const text = sibling.innerText.trim();
                                    if (text && text.length > 50) {
                                        description = text;
                                        break;
                                    }
                                }
                                sibling = sibling.nextElementSibling;
                                count++;
                            }
                            
                            recipients.push({
                                name: name,
                                description: description.substring(0, 500)
                            });
                        }
                    });
                    
                    // Get intro text
                    const introParagraphs = [];
                    const ps = document.querySelectorAll('article p, .article-body p');
                    ps.forEach(p => {
                        const text = p.innerText.trim();
                        if (text.includes('coronavirus') || text.includes('bursary') || text.includes('bursaries')) {
                            introParagraphs.push(text);
                        }
                    });
                    
                    return {
                        recipients: recipients,
                        intro: introParagraphs.slice(0, 3)
                    };
                }
            ''')
            
            return {
                'success': True,
                'data': {
                    'year': 2020,
                    'recipients': bursary_data['recipients'],
                    'total': len(bursary_data['recipients']),
                    'intro': bursary_data['intro'],
                    'source': 'https://www.tate.org.uk/art/turner-prize/turner-bursaries'
                }
            }
            
        finally:
            await browser.close()


async def get_year_details(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get details for a specific Turner Prize year.
    
    Required params:
    - year: The year to get details for (e.g., 2022)
    """
    year = params.get("year")
    
    if not year:
        return {
            'error': 'Missing required parameter: year',
            'example': {'year': 2022}
        }
    
    try:
        year = int(year)
    except (ValueError, TypeError):
        return {
            'error': f'Invalid year: {year}. Must be a number.'
        }
    
    # Get all years and filter
    result = await get_turner_prize_years({'start_year': year, 'end_year': year})
    
    if result.get('success') and result['data']['years']:
        return {
            'success': True,
            'data': result['data']['years'][0]
        }
    else:
        return {
            'error': f'No data found for year {year}',
            'available_years': '1984-2025'
        }