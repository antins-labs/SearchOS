"""
Ballotpedia Access Skill

Extracts biographical and political data from Ballotpedia pages including:
- Person infoboxes with structured data (name, party, education, etc.)
- Cabinet and officeholder listings
- Election results and term data

Note: Site uses AWS WAF protection requiring browser-based access.
"""

import asyncio
import re
from typing import Any, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class BallotpediaScraper:
    """Scraper for Ballotpedia with AWS WAF challenge handling."""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    
    async def init_browser(self):
        """Initialize browser if not already running."""
        if self.browser is None:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context(
                user_agent=self.user_agent
            )
    
    async def fetch_page(self, url: str, wait_time: int = 8) -> tuple[str, dict]:
        """
        Fetch a page, handling AWS WAF challenge.
        
        Returns:
            Tuple of (page_title, page_data)
        """
        await self.init_browser()
        
        page = await self.context.new_page()
        try:
            # Navigate and wait for WAF challenge
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(wait_time)
            
            title = await page.title()
            
            # Extract page data
            page_data = await page.evaluate('''
                () => {
                    const data = {
                        hasPersonInfobox: false,
                        hasMediaWiki: false,
                        sections: []
                    };
                    
                    // Check for MediaWiki content
                    const content = document.querySelector('.mw-parser-output');
                    data.hasMediaWiki = !!content;
                    data.htmlLength = document.body.innerHTML.length;
                    
                    // Get TOC sections
                    document.querySelectorAll('.toc li, #toc li').forEach(li => {
                        const text = li.textContent.trim();
                        if (text && text.length > 2 && text.length < 100) {
                            data.sections.push(text);
                        }
                    });
                    
                    return data;
                }
            ''')
            
            return title, page_data
            
        finally:
            await page.close()
    
    async def extract_person_data(self, url: str) -> dict[str, Any]:
        """
        Extract person infobox data from a Ballotpedia person page.
        
        Returns structured data including:
        - name, party, education, offices held
        - election history, net worth, religion
        """
        await self.init_browser()
        
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(8)
            
            result = await page.evaluate('''
                () => {
                    const data = {
                        success: false,
                        data: {},
                        raw_infobox: null
                    };
                    
                    // Find person infobox
                    const infobox = document.querySelector('div.infobox.person');
                    if (!infobox) {
                        data.error = 'No person infobox found';
                        return data;
                    }
                    
                    // Extract name from first value-only row
                    const nameRow = infobox.querySelector('.widget-row.value-only');
                    if (nameRow) {
                        const nameText = nameRow.textContent.trim();
                        // Usually first line is the name, might have party class
                        data.data.name = nameText.split('\\n')[0].trim();
                    }
                    
                    // Get party from link or text
                    const partyRow = infobox.querySelector('.widget-row.value-only.black, .widget-row.value-only.Republican, .widget-row.value-only.Democratic');
                    if (partyRow && !data.data.party) {
                        const partyLink = partyRow.querySelector('a[href*="Party"]');
                        if (partyLink) {
                            data.data.party = partyLink.textContent.trim();
                        } else {
                            const text = partyRow.textContent.trim();
                            if (text.includes('Party')) {
                                data.data.party = text;
                            }
                        }
                    }
                    
                    // Extract all key-value pairs from widget-rows
                    infobox.querySelectorAll('.widget-row').forEach(row => {
                        const labelEl = row.querySelector('.widget-key');
                        const valueEl = row.querySelector('.widget-value');
                        
                        if (labelEl && valueEl) {
                            const label = labelEl.textContent.trim().replace(/[:\\s]+$/, '');
                            const value = valueEl.textContent.trim();
                            
                            if (label && value) {
                                // Normalize label to snake_case
                                const key = label.toLowerCase()
                                    .replace(/[:\\s]+/g, '_')
                                    .replace(/[^a-z0-9_]/g, '');
                                data.data[key] = value;
                            }
                        }
                    });
                    
                    // Extract image
                    const img = infobox.querySelector('img[src*="ballotpedia"]');
                    if (img) {
                        data.data.image_url = img.src;
                    }
                    
                    // Extract prior offices
                    const priorOffices = [];
                    infobox.querySelectorAll('div').forEach(div => {
                        const style = div.getAttribute('style') || '';
                        if (style.includes('font-weight: bold') && style.includes('text-align: center')) {
                            const text = div.textContent.trim();
                            if (text && text.length < 100 && !text.includes('Prior offices')) {
                                priorOffices.push(text);
                            }
                        }
                    });
                    if (priorOffices.length > 0) {
                        data.data.prior_offices = priorOffices;
                    }
                    
                    // Also check for office holder links below infobox
                    const officeLinks = [];
                    infobox.querySelectorAll('a').forEach(a => {
                        const href = a.href;
                        const text = a.textContent.trim();
                        if (href && text && 
                            (href.includes('/U.S._House') || href.includes('/U.S._Senate') || 
                             href.includes('/Governor') || text.includes('District') ||
                             href.includes('/South_Carolina') || href.includes('/State'))) {
                            if (text.length > 2 && text.length < 100) {
                                officeLinks.push({text: text, href: href});
                            }
                        }
                    });
                    if (officeLinks.length > 0) {
                        data.data.office_links = officeLinks;
                    }
                    
                    data.success = true;
                    return data;
                }
            ''')
            
            return result
            
        finally:
            await page.close()
    
    async def extract_office_data(self, url: str) -> dict[str, Any]:
        """
        Extract office/cabinet data from a Ballotpedia office page.
        
        Returns lists of officeholders and their details.
        """
        await self.init_browser()
        
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(8)
            
            result = await page.evaluate('''
                () => {
                    const data = {
                        success: false,
                        title: document.title,
                        sections: [],
                        members: []
                    };
                    
                    const content = document.querySelector('.mw-parser-output');
                    if (!content) {
                        data.error = 'No content found';
                        return data;
                    }
                    
                    // Parse sections and members
                    let currentSection = null;
                    let currentMembers = [];
                    
                    content.childNodes.forEach(node => {
                        if (node.nodeType !== 1) return;
                        
                        const tag = node.tagName.toLowerCase();
                        const className = node.className || '';
                        
                        // H2 headings define sections
                        if (tag === 'h2') {
                            // Save previous section
                            if (currentSection && currentMembers.length > 0) {
                                data.sections.push({
                                    title: currentSection,
                                    members: currentMembers
                                });
                                currentMembers = [];
                            }
                            currentSection = node.textContent.trim()
                                .replace('[edit]', '').trim();
                        }
                        
                        // UL lists contain member info
                        if (tag === 'ul' && currentSection) {
                            node.querySelectorAll('li').forEach(li => {
                                const text = li.textContent.trim();
                                const link = li.querySelector('a[href*="ballotpedia.org/"]');
                                
                                // Filter for actual member entries
                                if (text.length > 20 && text.length < 500 && 
                                    (text.includes('Secretary') || text.includes('Director') ||
                                     text.includes('Attorney') || text.includes('President') ||
                                     text.includes('confirmed') || text.includes('sworn') ||
                                     text.includes('elected'))) {
                                    currentMembers.push({
                                        name: link ? link.textContent.trim() : null,
                                        link: link ? link.href : null,
                                        description: text
                                    });
                                }
                            });
                        }
                        
                        // Div.wrap elements contain person position cards
                        if (tag === 'div' && className.includes('wrap')) {
                            const text = node.textContent.trim();
                            if (text.length > 5 && text.length < 200) {
                                const link = node.querySelector('a[href*="ballotpedia.org/"]');
                                const img = node.querySelector('img');
                                
                                currentMembers.push({
                                    card: text,
                                    name: link ? link.textContent.trim() : text,
                                    link: link ? link.href : null,
                                    image: img ? img.src : null
                                });
                            }
                        }
                    });
                    
                    // Save last section
                    if (currentSection && currentMembers.length > 0) {
                        data.sections.push({
                            title: currentSection,
                            members: currentMembers
                        });
                    }
                    
                    data.success = true;
                    return data;
                }
            ''')
            
            return result
            
        finally:
            await page.close()
    
    async def extract_election_data(self, url: str) -> dict[str, Any]:
        """
        Extract election results tables from a Ballotpedia page.
        """
        await self.init_browser()
        
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(8)
            
            result = await page.evaluate('''
                () => {
                    const data = {
                        success: false,
                        elections: []
                    };
                    
                    // Find election result tables
                    document.querySelectorAll('table').forEach(table => {
                        const className = table.className || '';
                        const text = table.textContent || '';
                        
                        // Look for tables with election data
                        if (text.includes('Vote') && text.includes('%') &&
                            (className.includes('table') || className.includes('wikitable') ||
                             text.includes('Candidate') || text.includes('Party'))) {
                            
                            const election = {
                                className: className,
                                rows: []
                            };
                            
                            table.querySelectorAll('tr').forEach((tr, idx) => {
                                const cells = [];
                                tr.querySelectorAll('th, td').forEach(cell => {
                                    cells.push(cell.textContent.trim());
                                });
                                if (cells.length > 0) {
                                    election.rows.push(cells);
                                }
                            });
                            
                            if (election.rows.length > 1) {
                                data.elections.push(election);
                            }
                        }
                    });
                    
                    data.success = data.elections.length > 0;
                    return data;
                }
            ''')
            
            return result
            
        finally:
            await page.close()
    
    async def close(self):
        """Close browser resources."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.context = None


# Global scraper instance
_scraper: Optional[BallotpediaScraper] = None


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for Ballotpedia access skill.
    
    Parameters:
        url: The Ballotpedia URL to scrape
        function: One of 'person', 'office', 'election', 'page' (default: auto-detect)
        include_sections: Include page sections in response (default: false)
    
    Returns:
        Structured data extracted from the page
    """
    global _scraper
    
    url = params.get('url', '')
    function = params.get('function', 'auto')
    include_sections = params.get('include_sections', False)
    
    if not url:
        return {
            'success': False,
            'error': 'URL is required',
            'error_type': 'validation'
        }
    
    if 'ballotpedia.org' not in url:
        return {
            'success': False,
            'error': 'URL must be from ballotpedia.org',
            'error_type': 'validation'
        }
    
    try:
        # Initialize scraper
        if _scraper is None:
            _scraper = BallotpediaScraper()
        
        # Auto-detect function from URL
        if function == 'auto':
            # Person pages typically have the person's name as the last path segment
            path = url.split('/')[-1]
            
            # Cabinet/office pages have specific patterns
            if 'Cabinet' in path or 'office' in path.lower():
                function = 'office'
            # Election pages
            elif 'election' in path.lower() or 'result' in path.lower():
                function = 'election'
            else:
                # Default to person for most Ballotpedia pages
                function = 'person'
        
        # Execute appropriate function
        if function == 'person':
            result = await _scraper.extract_person_data(url)
        elif function == 'office':
            result = await _scraper.extract_office_data(url)
        elif function == 'election':
            result = await _scraper.extract_election_data(url)
        elif function == 'page':
            title, page_data = await _scraper.fetch_page(url)
            result = {
                'success': True,
                'title': title,
                'data': page_data
            }
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}',
                'error_type': 'validation'
            }
        
        # Add sections if requested
        if include_sections and result.get('success'):
            _, page_data = await _scraper.fetch_page(url)
            result['sections'] = page_data.get('sections', [])
        
        return result
        
    except asyncio.TimeoutError:
        return {
            'success': False,
            'error': 'Request timed out (AWS WAF challenge may have failed)',
            'error_type': 'timeout'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'error_type': 'scraping_error'
        }


# For testing
async def main():
    """Test the executor with sample URLs."""
    test_urls = [
        ('https://ballotpedia.org/Mick_Mulvaney', 'person'),
        ('https://ballotpedia.org/Alex_Azar', 'person'),
        ('https://ballotpedia.org/Donald_Trump_presidential_Cabinet,_2017-2021', 'office'),
    ]
    
    for url, expected_type in test_urls:
        print(f"\n{'='*80}")
        print(f"Testing: {url}")
        print('='*80)
        
        result = await execute({'url': url, 'function': expected_type})
        
        if result.get('success'):
            print(f"SUCCESS - Type: {expected_type}")
            if expected_type == 'person':
                data = result.get('data', {})
                print(f"  Name: {data.get('name', 'N/A')}")
                print(f"  Party: {data.get('party', 'N/A')}")
                print(f"  Education: {data.get('education', data.get("bachelor's", 'N/A'))}")
                print(f"  Keys found: {list(data.keys())[:15]}")
            elif expected_type == 'office':
                sections = result.get('sections', [])
                print(f"  Sections found: {len(sections)}")
                for section in sections[:3]:
                    print(f"    - {section['title']}: {len(section['members'])} members")
        else:
            print(f"FAILED: {result.get('error', 'Unknown error')}")
    
    # Clean up
    if _scraper:
        await _scraper.close()


if __name__ == '__main__':
    asyncio.run(main())