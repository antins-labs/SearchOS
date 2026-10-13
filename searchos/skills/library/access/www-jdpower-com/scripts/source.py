"""
J.D. Power Vehicle Ratings Access Skill

Extracts vehicle ratings, awards, and specifications from J.D. Power website.
Supports multiple study types: Dependability, Quality, Performance, etc.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright, Browser, Page


async def fetch_ratings_study(study_name: str, year: int) -> Dict[str, Any]:
    """
    Extract vehicle ratings and award winners from a J.D. Power study.
    
    Args:
        study_name: Study type (e.g., 'dependability', 'quality', 'performance')
        year: Model year (e.g., 2024, 2025)
    
    Returns:
        Dictionary containing brand ratings and segment winners
    """
    url = f"https://www.jdpower.com/cars/ratings/{study_name}/{year}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)  # Wait for dynamic content
            
            title = await page.title()
            if 'Cloudflare' in title or 'blocked' in title.lower():
                await browser.close()
                return {
                    'error': 'Access blocked by Cloudflare',
                    'url': url,
                    'study': study_name,
                    'year': year
                }
            
            result = await page.evaluate("""(studyName) => {
                const results = {
                    study: studyName,
                    year: parseInt(window.location.pathname.split('/').filter(s => s)[3]) || new Date().getFullYear(),
                    url: window.location.href,
                    title: document.title,
                    brand_ratings: [],
                    segment_winners: {}
                };
                
                // Helper to process vehicle grid
                function processVehicleGrid(container) {
                    const vehicles = [];
                    const links = container.querySelectorAll('a[href^="/cars/"]');
                    
                    links.forEach(link => {
                        const href = link.getAttribute('href');
                        const text = link.textContent.trim();
                        
                        // Skip brand links
                        if (href.match(/\\/cars\\/\\d{4}\\/[^\\/]+$/)) return;
                        
                        const match = href.match(/\\/cars\\/(\\d{4})\\/([^\\/]+)\\/([^\\/]+)/);
                        if (match) {
                            let category = 'Vehicle';
                            const parts = text.split(/\\d{4}/);
                            if (parts[0] && parts[0].trim()) {
                                category = parts[0].trim();
                            }
                            
                            vehicles.push({
                                category: category,
                                year: match[1],
                                make: match[2].replace(/-/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase()),
                                model: match[3].replace(/-/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase()),
                                url: 'https://www.jdpower.com' + href
                            });
                        }
                    });
                    
                    return vehicles;
                }
                
                // Extract brand ratings
                const allH2 = document.querySelectorAll('h2');
                allH2.forEach(h2 => {
                    const text = h2.textContent.trim();
                    
                    if (text.includes('Highest Rated') && text.includes('Brands')) {
                        const parent = h2.parentElement;
                        const links = parent.querySelectorAll('a[href*="/cars/"]');
                        let rank = 1;
                        links.forEach(link => {
                            const href = link.getAttribute('href');
                            const linkText = link.textContent.trim();
                            const match = href.match(/\\/cars\\/(\\d{4})\\/([^\\/]+)$/);
                            if (match && linkText.length > 2 && linkText.length < 30) {
                                results.brand_ratings.push({
                                    rank: rank++,
                                    make: match[2].replace(/-/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase()),
                                    year: match[1],
                                    url: 'https://www.jdpower.com' + href
                                });
                            }
                        });
                    }
                    
                    // Extract segment winners
                    if (text.includes('Highest')) {
                        const match = text.match(/Highest (\\w+) (\\w+) Vehicles/);
                        if (match) {
                            const segmentName = match[2];
                            
                            let container = h2.parentElement;
                            for (let i = 0; i < 10; i++) {
                                if (!container) break;
                                
                                const awardH3 = container.querySelector('h3');
                                if (awardH3 && awardH3.textContent.includes('Award Winners')) {
                                    const grids = container.querySelectorAll('[class*="grid"], [class*="card"]');
                                    let vehicles = [];
                                    
                                    grids.forEach(grid => {
                                        const gridVehicles = processVehicleGrid(grid);
                                        vehicles = vehicles.concat(gridVehicles);
                                    });
                                    
                                    if (vehicles.length > 0) {
                                        results.segment_winners[segmentName] = vehicles;
                                    }
                                    break;
                                }
                                
                                container = container.parentElement;
                            }
                        }
                    }
                });
                
                return results;
            }""", study_name)
            
            await browser.close()
            return result
            
        except Exception as e:
            await browser.close()
            return {
                'error': str(e),
                'url': url,
                'study': study_name,
                'year': year
            }


async def fetch_vehicle_page(year: int, make: str, model: str) -> Dict[str, Any]:
    """
    Extract vehicle specifications and ratings from a specific vehicle page.
    
    Args:
        year: Model year
        make: Vehicle make (e.g., 'toyota')
        model: Vehicle model (e.g., 'corolla')
    
    Returns:
        Dictionary containing vehicle ratings and specifications
    """
    make_slug = make.lower().replace(' ', '-')
    model_slug = model.lower().replace(' ', '-')
    url = f"https://www.jdpower.com/cars/{year}/{make_slug}/{model_slug}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)
            
            title = await page.title()
            if 'Cloudflare' in title or 'blocked' in title.lower():
                await browser.close()
                return {
                    'error': 'Access blocked by Cloudflare',
                    'url': url,
                    'year': year,
                    'make': make,
                    'model': model
                }
            
            # Extract vehicle data
            result = await page.evaluate("""() => {
                const data = {
                    url: window.location.href,
                    title: document.title,
                    year: null,
                    make: null,
                    model: null,
                    ratings: [],
                    specs: {},
                    sections: []
                };
                
                // Try to extract year/make/model from URL
                const urlMatch = window.location.pathname.match(/\\/cars\\/(\\d{4})\\/([^\\/]+)\\/([^\\/]+)/);
                if (urlMatch) {
                    data.year = urlMatch[1];
                    data.make = urlMatch[2].replace(/-/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase());
                    data.model = urlMatch[3].replace(/-/g, ' ').replace(/\\b\\w/g, l => l.toUpperCase());
                }
                
                // Extract ratings from the page
                const ratingElements = document.querySelectorAll('[class*="rating"], [class*="score"], [class*="point"]');
                ratingElements.forEach(elem => {
                    const text = elem.textContent.trim();
                    if (text && text.length > 5 && text.length < 100) {
                        // Look for rating patterns
                        const scoreMatch = text.match(/(\\d+(?:\\.\\d+)?)\\s*(?:out\\s+of|\\/)?\\s*(\\d+)/);
                        if (scoreMatch) {
                            data.ratings.push({
                                text: text,
                                score: parseFloat(scoreMatch[1]),
                                max_score: parseFloat(scoreMatch[2])
                            });
                        }
                    }
                });
                
                // Extract headings for sections
                const headings = document.querySelectorAll('h1, h2, h3');
                headings.forEach(h => {
                    const text = h.textContent.trim();
                    if (text && text.length > 5 && text.length < 100) {
                        data.sections.push(text);
                    }
                });
                
                return data;
            }""")
            
            await browser.close()
            return result
            
        except Exception as e:
            await browser.close()
            return {
                'error': str(e),
                'url': url,
                'year': year,
                'make': make,
                'model': model
            }


async def list_available_studies() -> Dict[str, Any]:
    """
    List available J.D. Power rating studies.
    
    Returns:
        Dictionary containing available studies and years
    """
    return {
        'studies': [
            {
                'name': 'dependability',
                'title': 'Vehicle Dependability Study (VDS)',
                'description': 'Measures problems experienced by original owners of 3-year-old vehicles',
                'url_pattern': 'https://www.jdpower.com/cars/ratings/dependability/{year}',
                'available_years': [2024, 2025]
            },
            {
                'name': 'quality',
                'title': 'Initial Quality Study (IQS)',
                'description': 'Measures problems experienced by original owners of new vehicles',
                'url_pattern': 'https://www.jdpower.com/cars/ratings/quality/{year}',
                'available_years': [2024]
            },
            {
                'name': 'performance',
                'title': 'APEAL Study',
                'description': 'Measures owner emotional attachment and level of excitement with new vehicle',
                'url_pattern': 'https://www.jdpower.com/cars/ratings/performance/{year}',
                'available_years': [2024]
            }
        ],
        'note': 'Years may vary based on study release schedule'
    }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for J.D. Power access skill.
    
    Parameters (in params dict):
        function: str - Required. One of:
            - 'get_ratings': Get ratings for a specific study and year
            - 'get_vehicle': Get details for a specific vehicle
            - 'list_studies': List available studies
        
        For 'get_ratings':
            study: str - Required. Study type (e.g., 'dependability', 'quality', 'performance')
            year: int - Required. Model year (e.g., 2024, 2025)
        
        For 'get_vehicle':
            year: int - Required. Model year
            make: str - Required. Vehicle make (e.g., 'toyota')
            model: str - Required. Vehicle model (e.g., 'corolla')
    
    Returns:
        Dictionary with success status and data or error message
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function',
            'valid_functions': ['get_ratings', 'get_vehicle', 'list_studies']
        }
    
    if function == 'list_studies':
        result = await list_available_studies()
        return {
            'success': True,
            'data': result
        }
    
    elif function == 'get_ratings':
        study = params.get('study', '').lower()
        year = params.get('year')
        
        if not study:
            return {
                'success': False,
                'error': 'Missing required parameter: study',
                'valid_studies': ['dependability', 'quality', 'performance']
            }
        
        if not year:
            return {
                'success': False,
                'error': 'Missing required parameter: year',
                'example': 2025
            }
        
        year = int(year)
        
        if study not in ['dependability', 'quality', 'performance']:
            return {
                'success': False,
                'error': f'Invalid study: {study}',
                'valid_studies': ['dependability', 'quality', 'performance']
            }
        
        result = await fetch_ratings_study(study, year)
        
        if 'error' in result:
            return {
                'success': False,
                'error': result['error'],
                'url': result.get('url'),
                'study': study,
                'year': year
            }
        
        return {
            'success': True,
            'data': result
        }
    
    elif function == 'get_vehicle':
        year = params.get('year')
        make = params.get('make', '').lower().replace(' ', '-')
        model = params.get('model', '').lower().replace(' ', '-')
        
        if not year:
            return {
                'success': False,
                'error': 'Missing required parameter: year'
            }
        
        if not make:
            return {
                'success': False,
                'error': 'Missing required parameter: make'
            }
        
        if not model:
            return {
                'success': False,
                'error': 'Missing required parameter: model'
            }
        
        year = int(year)
        
        result = await fetch_vehicle_page(year, make, model)
        
        if 'error' in result:
            return {
                'success': False,
                'error': result['error'],
                'url': result.get('url'),
                'year': year,
                'make': make,
                'model': model
            }
        
        return {
            'success': True,
            'data': result
        }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}',
            'valid_functions': ['get_ratings', 'get_vehicle', 'list_studies']
        }


# For testing
if __name__ == '__main__':
    import sys
    
    async def test():
        # Test list studies
        print("=== Testing list_studies ===")
        result = await execute({'function': 'list_studies'})
        print(json.dumps(result, indent=2))
        
        # Test get ratings
        print("\n=== Testing get_ratings (dependability) ===")
        result = await execute({'function': 'get_ratings', 'study': 'dependability', 'year': 2025})
        print(f"Success: {result['success']}")
        if result['success']:
            data = result['data']
            print(f"Study: {data['study']}")
            print(f"Year: {data['year']}")
            print(f"Brand ratings: {len(data['brand_ratings'])}")
            print(f"Segments: {list(data['segment_winners'].keys())}")
        else:
            print(f"Error: {result['error']}")
        
        # Test get vehicle
        print("\n=== Testing get_vehicle ===")
        result = await execute({'function': 'get_vehicle', 'year': 2022, 'make': 'toyota', 'model': 'corolla'})
        print(f"Success: {result['success']}")
        if result['success']:
            data = result['data']
            print(f"Title: {data['title']}")
            print(f"Vehicle: {data['year']} {data['make']} {data['model']}")
            print(f"Ratings found: {len(data['ratings'])}")
        else:
            print(f"Error: {result['error']}")
    
    asyncio.run(test())