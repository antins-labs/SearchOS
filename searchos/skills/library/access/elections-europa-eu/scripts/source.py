"""
Elections Europa EU - How to Vote Access Skill

Retrieves country-specific voting information from the European Parliament 
elections website (elections.europa.eu).

The site uses a structured expand/collapse accordion pattern for Q&A sections,
which requires JavaScript rendering and DOM parsing to extract properly.
"""

from __future__ import annotations
from typing import Any
import re


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute the elections.europa.eu access skill.
    
    Args:
        params: Dictionary with 'function' key and function-specific parameters

    
    Returns:
        Dict with structured voting information or error details
    """
    function = params.get("function", "")
    
    if function == "get_country_voting_info":
        return await _get_country_voting_info(params)
    elif function == "list_available_countries":
        return await _list_available_countries(params)
    else:
        return {
            "error": f"Unknown function: {function}",
            "available_functions": ["get_country_voting_info", "list_available_countries"]
        }


async def _get_country_voting_info(params: dict[str, Any]) -> dict[str, Any]:
    """
    Retrieve voting information for a specific EU country.
    
    Args:
        country_code: Two-letter country code (e.g., 'fr', 'de', 'it', 'gr')
        language: Optional language code (default: 'en')
        sections: Optional list of specific sections to retrieve (default: all)
    
    Returns:
        Dict with country voting information including Q&A sections
    """
    country_code = params.get("country_code", "").lower().strip()
    language = params.get("language", "en").lower().strip()
    requested_sections = params.get("sections")  # Optional filter
    
    if not country_code:
        return {
            "error": "Missing required parameter: country_code",
            "usage": "Provide a two-letter country code (e.g., 'fr', 'de', 'it', 'gr')"
        }
    
    # Validate country code format
    if not re.match(r'^[a-z]{2}$', country_code):
        return {
            "error": f"Invalid country_code format: '{country_code}'",
            "usage": "Use a two-letter ISO country code (e.g., 'fr', 'de', 'it', 'gr')"
        }
    
    # Build URL
    url = f"https://elections.europa.eu/{language}/how-to-vote/{country_code}/"
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                
                # Navigate to the page
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(1500)
                
                # Check if page loaded correctly
                title = await page.title()
                if "404" in title or "not found" in title.lower():
                    return {
                        "error": f"Country page not found: {country_code}",
                        "url": url,
                        "suggestion": "The country code may be invalid or the page may not exist"
                    }
                
                # Extract structured data
                data = await page.evaluate('''() => {
                    const result = {
                        title: '',
                        intro: '',
                        lastReviewed: '',
                        sections: [],
                        url: window.location.href
                    };
                    
                    // Get title
                    const h1 = document.querySelector('h1');
                    result.title = h1 ? h1.innerText.trim() : '';
                    
                    // Get intro text - find the main description paragraph
                    if (h1) {
                        const bodyText = document.body.innerText;
                        const lines = bodyText.split('\\n').map(l => l.trim()).filter(l => l.length > 30);
                        
                        for (const line of lines) {
                            if ((line.includes('elections take place') || 
                                 line.includes('European elections') ||
                                 line.includes('aged 18') ||
                                 line.includes('polling stations')) &&
                                !line.startsWith('What') && !line.startsWith('How') && 
                                !line.startsWith('Who') && !line.startsWith('Where') &&
                                !line.startsWith('Can I') && !line.startsWith('Is there')) {
                                result.intro = line;
                                break;
                            }
                        }
                    }
                    
                    // Get last reviewed date
                    const bodyText = document.body.innerText;
                    const reviewedMatch = bodyText.match(/Last reviewed:\\s*([\\d\\/]+)/i);
                    if (reviewedMatch) {
                        result.lastReviewed = reviewedMatch[1];
                    }
                    
                    // Extract Q&A sections using the expand/collapse DOM structure
                    // Each section is: LI.expand-container > H2 + DIV.expand-container-content
                    const sections = document.querySelectorAll('li.expand-container');
                    
                    sections.forEach(section => {
                        const h2 = section.querySelector('h2');
                        const contentDiv = section.querySelector('.expand-container-content');
                        
                        if (h2 && contentDiv) {
                            const question = h2.innerText.trim();
                            if (question.toLowerCase().includes('top action')) return;
                            
                            let answer = contentDiv.innerText.trim();
                            // Clean up share buttons text
                            answer = answer
                                .replace(/Share\\n?/g, '')
                                .replace(/on Facebook[^\\n]*/g, '')
                                .replace(/on Twiter[^\\n]*/g, '')
                                .replace(/\\s+/g, ' ')
                                .trim();
                            
                            if (answer.length > 10) {
                                result.sections.push({ 
                                    question: question, 
                                    answer: answer 
                                });
                            }
                        }
                    });
                    
                    return result;
                }''')
                
                # Filter sections if requested
                if requested_sections and isinstance(requested_sections, list):
                    filtered = []
                    for section in data['sections']:
                        q_lower = section['question'].lower()
                        for req in requested_sections:
                            if req.lower() in q_lower:
                                filtered.append(section)
                                break
                    data['sections'] = filtered
                
                # Add metadata
                data['country_code'] = country_code
                data['language'] = language
                data['source_url'] = url
                data['success'] = True
                
                return data
                
            finally:
                await browser.close()
                
    except Exception as e:
        return {
            "error": f"Failed to retrieve voting info: {type(e).__name__}",
            "details": str(e),
            "url": url,
            "country_code": country_code
        }


async def _list_available_countries(params: dict[str, Any]) -> dict[str, Any]:
    """
    List available EU country codes for voting information.
    
    Returns:
        Dict with list of country codes and names
    """
    # EU member country codes (ISO 3166-1 alpha-2)
    eu_countries = {
        "at": "Austria",
        "be": "Belgium",
        "bg": "Bulgaria",
        "hr": "Croatia",
        "cy": "Cyprus",
        "cz": "Czech Republic",
        "dk": "Denmark",
        "ee": "Estonia",
        "fi": "Finland",
        "fr": "France",
        "de": "Germany",
        "gr": "Greece",
        "hu": "Hungary",
        "ie": "Ireland",
        "it": "Italy",
        "lv": "Latvia",
        "lt": "Lithuania",
        "lu": "Luxembourg",
        "mt": "Malta",
        "nl": "Netherlands",
        "pl": "Poland",
        "pt": "Portugal",
        "ro": "Romania",
        "sk": "Slovakia",
        "si": "Slovenia",
        "es": "Spain",
        "se": "Sweden"
    }
    
    return {
        "success": True,
        "countries": eu_countries,
        "total": len(eu_countries),
        "note": "Use the two-letter country code with get_country_voting_info function"
    }