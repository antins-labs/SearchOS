"""
CUHK Business School Masters Programs Scraper

This skill extracts program information from the CUHK Business School masters programs website.
The site uses aggressive anti-bot protection (Incapsula/Imperva), so this scraper uses
Playwright with proper browser fingerprinting to avoid detection.

Programs available:
- MAcc (Master of Accountancy)
- MIM (MSc in Management)
- MScBA (MSc in Business Analytics)
- MScFin (MSc in Finance)
- MScITM (MSc in Information and Technology Management)
- MScMKT (MSc in Marketing)
- MScRE (MSc in Real Estate)
- And more...
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

# Try to import playwright, handle if not available
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# Known program slugs
PROGRAM_SLUGS = {
    "macc": {"name": "Master of Accountancy", "url": "https://masters.bschool.cuhk.edu.hk/programmes/macc/"},
    "mam": {"name": "Master in Management", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mam/"},
    "mim": {"name": "MSc in Management", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mim/"},
    "mscasi": {"name": "MSc in Accounting and Finance", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscasi/"},
    "mscba": {"name": "MSc in Business Analytics", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscba/"},
    "mscfbm": {"name": "MSc in Family Business Management", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscfbm/"},
    "mscfin": {"name": "MSc in Finance", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscfin/"},
    "mscgwm": {"name": "MSc in Global Wealth Management", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscgwm/"},
    "mscistm": {"name": "MSc in Information Systems Management", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscistm/"},
    "mscitm": {"name": "MSc in Information and Technology Management", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscitm/"},
    "msclee": {"name": "MSc in Leadership for Experience Economy", "url": "https://masters.bschool.cuhk.edu.hk/programmes/msclee/"},
    "mscmkt": {"name": "MSc in Marketing", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscmkt/"},
    "mscre": {"name": "MSc in Real Estate", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscre/"},
    "mscsbm": {"name": "MSc in Sports Business Management", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscsbm/"},
    "mscsgb": {"name": "MSc in Sustainable Global Business", "url": "https://masters.bschool.cuhk.edu.hk/programmes/mscsgb/"},
}


async def create_stealth_browser():
    """Create a browser instance with anti-detection measures"""
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed. Install with: pip install playwright && playwright install chromium")
    
    p = await async_playwright().start()
    
    browser = await p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--window-size=1920,1080',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
        ]
    )
    
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        locale='en-US',
        timezone_id='Asia/Hong_Kong',
    )
    
    # Inject stealth scripts
    await context.add_init_script("""
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        
        // Fake plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
            ]
        });
        
        // Fake languages
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'zh-HK', 'zh']});
        
        // Fake platform
        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        
        // Fake hardware concurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
        
        // Fake device memory
        Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
        
        // Remove automation indicators
        window.chrome = { runtime: {} };
        
        // Fake permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)
    
    return p, browser, context


async def extract_program_data(page: Page, slug: str, url: str) -> Dict[str, Any]:
    """Extract comprehensive program information from a page"""
    
    try:
        # Navigate with timeout
        response = await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        
        if response and response.status == 404:
            return {
                "success": False,
                "error": "Page not found (404)",
                "slug": slug,
                "url": url,
                "program_name": PROGRAM_SLUGS.get(slug, {}).get("name", slug)
            }
        
        # Wait for content to load
        await page.wait_for_timeout(5000)
        
        # Check for captcha/blocked page
        title = await page.title()
        current_url = page.url
        
        if "Robot Challenge" in title or "sgcaptcha" in current_url.lower():
            return {
                "success": False,
                "error": "Site triggered anti-bot protection. Please try again later or with a different IP.",
                "slug": slug,
                "url": url,
                "program_name": PROGRAM_SLUGS.get(slug, {}).get("name", slug)
            }
        
        if "404" in title or "not found" in title.lower():
            return {
                "success": False,
                "error": "Page not found",
                "slug": slug,
                "url": url,
                "program_name": PROGRAM_SLUGS.get(slug, {}).get("name", slug)
            }
        
        # Extract all program data
        data = await page.evaluate('''
            () => {
                const result = {
                    url: window.location.href,
                    title: document.title,
                    meta: {},
                    json_ld: [],
                    headings: [],
                    overview: null,
                    curriculum: null,
                    courses: [],
                    admission: null,
                    tuition: null,
                    careers: null,
                    contact: null,
                    paragraphs: [],
                    lists: [],
                    tables: [],
                    main_text: null
                };
                
                // Get meta tags
                document.querySelectorAll('meta').forEach(meta => {
                    const name = meta.getAttribute('name') || meta.getAttribute('property') || meta.getAttribute('itemprop');
                    const content = meta.getAttribute('content');
                    if (name && content) {
                        result.meta[name] = content;
                    }
                });
                
                // Extract JSON-LD
                document.querySelectorAll('script[type="application/ld+json"]').forEach(script => {
                    try {
                        const data = JSON.parse(script.textContent);
                        if (Array.isArray(data['@graph'])) {
                            result.json_ld = data['@graph'];
                        } else {
                            result.json_ld.push(data);
                        }
                    } catch (e) {}
                });
                
                // Get all headings
                result.headings = Array.from(document.querySelectorAll('h1, h2, h3, h4')).map(h => ({
                    tag: h.tagName,
                    text: h.innerText?.trim(),
                    id: h.id,
                    className: h.className
                }));
                
                // Get main content text
                const main = document.querySelector('main, article, .single-programme, .programme-content, #primary, .content');
                if (main) {
                    result.main_text = main.innerText;
                }
                
                // Get overview/intro - usually first paragraph after title
                const overviewSelectors = [
                    '.overview', '.intro', '.programme-intro', '.header-content',
                    '.entry-content > p:first-of-type', 'article p:first-of-type'
                ];
                for (const sel of overviewSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText?.trim().length > 50) {
                        result.overview = el.innerText.trim();
                        break;
                    }
                }
                
                // Get curriculum section
                const curriculumSelectors = ['.curriculum', '#curriculum', '[class*="curriculum"]', '#tab-curriculum'];
                for (const sel of curriculumSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText?.trim().length > 100) {
                        result.curriculum = el.innerText.trim();
                        break;
                    }
                }
                
                // Extract courses from curriculum
                document.querySelectorAll('.curriculum li, [class*="curriculum"] li, .course-list li, [class*="course"] li').forEach(li => {
                    const course = li.innerText?.trim();
                    if (course && course.length > 5 && course.length < 500) {
                        result.courses.push(course);
                    }
                });
                
                // Get admission section
                const admissionSelectors = ['.admission', '#admission', '[class*="admission"]', '[class*="deadline"]', '#tab-admissions'];
                for (const sel of admissionSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText?.trim().length > 100) {
                        result.admission = el.innerText.trim();
                        break;
                    }
                }
                
                // Get tuition/fees
                const feeSelectors = ['[class*="tuition"]', '[class*="fee"]', '[class*="scholarship"]'];
                for (const sel of feeSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const text = el.innerText?.trim();
                        if (text && (text.includes('HK$') || text.includes('fee') || text.includes('Fee'))) {
                            result.tuition = text;
                            break;
                        }
                    }
                }
                
                // Get career section
                const careerSelectors = ['.career', '#careers', '[class*="career"]', '#tab-careers'];
                for (const sel of careerSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText?.trim().length > 100) {
                        result.careers = el.innerText.trim();
                        break;
                    }
                }
                
                // Get contact section
                const contactSelectors = ['.contact', '#contact', '[class*="contact"]'];
                for (const sel of contactSelectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText?.trim().length > 50) {
                        result.contact = el.innerText.trim();
                        break;
                    }
                }
                
                // Get paragraphs
                result.paragraphs = Array.from(document.querySelectorAll('p'))
                    .map(p => p.innerText?.trim())
                    .filter(t => t && t.length > 30)
                    .slice(0, 50);
                
                // Get lists
                result.lists = Array.from(document.querySelectorAll('ul, ol'))
                    .map(list => ({
                        className: list.className,
                        items: Array.from(list.querySelectorAll('li'))
                            .map(li => li.innerText?.trim())
                            .filter(t => t && t.length < 500)
                            .slice(0, 20)
                    }))
                    .filter(l => l.items.length > 0)
                    .slice(0, 20);
                
                // Get tables
                result.tables = Array.from(document.querySelectorAll('table'))
                    .map(table => {
                        const rows = Array.from(table.querySelectorAll('tr')).map(tr => 
                            Array.from(tr.querySelectorAll('td, th')).map(cell => cell.innerText?.trim())
                        );
                        return { rows };
                    })
                    .filter(t => t.rows.length > 0);
                
                return result;
            }
        ''')
        
        # Build result
        program_name = data.get('title', '').split(' - ')[0].strip()
        
        return {
            "success": True,
            "slug": slug,
            "url": url,
            "title": data.get('title', ''),
            "program_name": program_name,
            "description": data.get('meta', {}).get('description'),
            "overview": data.get('overview'),
            "curriculum": data.get('curriculum'),
            "courses": data.get('courses', []),
            "admission": data.get('admission'),
            "tuition": data.get('tuition'),
            "careers": data.get('careers'),
            "contact": data.get('contact'),
            "headings": data.get('headings', []),
            "meta": data.get('meta', {}),
            "json_ld": data.get('json_ld', []),
            "paragraphs": data.get('paragraphs', []),
            "lists": data.get('lists', []),
            "tables": data.get('tables', []),
            "main_text": data.get('main_text'),
            "extracted_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "slug": slug,
            "url": url,
            "program_name": PROGRAM_SLUGS.get(slug, {}).get("name", slug)
        }


async def list_all_programs(ctx: Any = None) -> Dict[str, Any]:
    """List all available programs"""
    programs = []
    for slug, info in PROGRAM_SLUGS.items():
        programs.append({
            "slug": slug,
            "name": info["name"],
            "url": info["url"]
        })
    
    return {
        "success": True,
        "count": len(programs),
        "programs": programs,
        "source": "https://masters.bschool.cuhk.edu.hk/"
    }


async def get_program(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Get detailed information about a specific program"""
    
    slug = params.get("slug", "").lower().strip()
    
    if not slug:
        return {
            "success": False,
            "error": "Parameter 'slug' is required. Use 'list_programs' to see available programs."
        }
    
    # Handle common variations
    slug_mapping = {
        "business-analytics": "mscba",
        "msc-business-analytics": "mscba",
        "msc business analytics": "mscba",
        "finance": "mscfin",
        "msc-finance": "mscfin",
        "msc finance": "mscfin",
        "accountancy": "macc",
        "accounting": "macc",
        "marketing": "mscmkt",
        "management": "mim",
    }
    
    if slug in slug_mapping:
        slug = slug_mapping[slug]
    
    if slug not in PROGRAM_SLUGS:
        return {
            "success": False,
            "error": f"Unknown program slug: '{slug}'. Use 'list_programs' to see available programs.",
            "available_slugs": list(PROGRAM_SLUGS.keys())
        }
    
    # Check if Playwright is available
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "success": False,
            "error": "Playwright not installed. Install with: pip install playwright && playwright install chromium",
            "program_slug": slug,
            "program_name": PROGRAM_SLUGS[slug]["name"],
            "url": PROGRAM_SLUGS[slug]["url"]
        }
    
    p = None
    try:
        # Create browser
        p, browser, context = await create_stealth_browser()
        page = await context.new_page()
        
        # Extract program data
        url = PROGRAM_SLUGS[slug]["url"]
        result = await extract_program_data(page, slug, url)
        
        await browser.close()
        if p:
            await p.stop()
        
        return result
        
    except Exception as e:
        if p:
            try:
                await p.stop()
            except:
                pass
        return {
            "success": False,
            "error": f"Failed to extract program data: {str(e)}",
            "slug": slug,
            "url": PROGRAM_SLUGS.get(slug, {}).get("url", "")
        }


async def search_programs(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Search for programs by keyword"""
    
    query = params.get("query", "").lower().strip()
    
    if not query:
        return {
            "success": False,
            "error": "Parameter 'query' is required"
        }
    
    results = []
    for slug, info in PROGRAM_SLUGS.items():
        name = info["name"].lower()
        if query in name or query in slug:
            results.append({
                "slug": slug,
                "name": info["name"],
                "url": info["url"],
                "relevance": "high" if query in name else "medium"
            })
    
    return {
        "success": True,
        "query": query,
        "count": len(results),
        "results": results
    }


async def get_multiple_programs(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Get information about multiple programs at once"""
    
    slugs = params.get("slugs", [])
    
    if not slugs:
        return {
            "success": False,
            "error": "Parameter 'slugs' (list) is required"
        }
    
    # Validate slugs
    invalid = [s for s in slugs if s.lower() not in PROGRAM_SLUGS]
    if invalid:
        return {
            "success": False,
            "error": f"Invalid program slugs: {invalid}",
            "available_slugs": list(PROGRAM_SLUGS.keys())
        }
    
    if not PLAYWRIGHT_AVAILABLE:
        return {
            "success": False,
            "error": "Playwright not installed. Install with: pip install playwright && playwright install chromium"
        }
    
    p = None
    try:
        p, browser, context = await create_stealth_browser()
        page = await context.new_page()
        
        results = []
        for slug in slugs:
            slug = slug.lower()
            url = PROGRAM_SLUGS[slug]["url"]
            
            # Add delay between requests to avoid triggering anti-bot
            if len(results) > 0:
                await page.wait_for_timeout(3000)
            
            result = await extract_program_data(page, slug, url)
            results.append(result)
        
        await browser.close()
        if p:
            await p.stop()
        
        success_count = len([r for r in results if r.get('success')])
        
        return {
            "success": True,
            "requested": len(slugs),
            "extracted": success_count,
            "failed": len(slugs) - success_count,
            "programs": results
        }
        
    except Exception as e:
        if p:
            try:
                await p.stop()
            except:
                pass
        return {
            "success": False,
            "error": str(e)
        }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """Main entry point for the skill"""
    
    function = params.get("function", "")
    
    if not function:
        return {
            "success": False,
            "error": "Parameter 'function' is required. Available functions: list_programs, get_program, search_programs, get_multiple_programs"
        }
    
    if function == "list_programs":
        return await list_all_programs(ctx)
    elif function == "get_program":
        return await get_program(params, ctx)
    elif function == "search_programs":
        return await search_programs(params, ctx)
    elif function == "get_multiple_programs":
        return await get_multiple_programs(params, ctx)
    else:
        return {
            "success": False,
            "error": f"Unknown function: '{function}'. Available functions: list_programs, get_program, search_programs, get_multiple_programs"
        }