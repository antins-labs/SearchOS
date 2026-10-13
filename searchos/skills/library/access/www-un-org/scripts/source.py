"""
UN Member States and Organ Membership Data Access Skill

Fetches structured data from United Nations official website:
- List of all UN member states with admission dates
- Security Council membership (permanent and non-permanent)
- International Court of Justice judges

Uses direct HTTP requests for member states (reliable) and Playwright
for pages that may require JavaScript rendering.
"""

import asyncio
import re
from typing import Any
from bs4 import BeautifulSoup

# Use httpx for async HTTP
import httpx


async def fetch_member_states() -> dict[str, Any]:
    """
    Fetch list of all UN member states with admission dates.
    
    Returns:
        dict with 'count' and 'members' list containing:
        - name: country name
        - admission_date: date in DD-MM-YYYY format
    """
    url = "https://www.un.org/en/about-us/member-states"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            follow_redirects=True
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find all country cards
        country_divs = soup.find_all('div', class_='country')
        
        members = []
        for div in country_divs:
            # Get the country name from h2
            h2 = div.find('h2')
            name = h2.get_text(strip=True) if h2 else None
            
            # Get the date of admission
            text = div.get_text()
            date_match = re.search(r'Date of Admission:\s*(\d{2}-\d{2}-\d{4})', text)
            admission_date = date_match.group(1) if date_match else None
            
            if name:
                members.append({
                    'name': name,
                    'admission_date': admission_date
                })
        
        return {
            'count': len(members),
            'members': members
        }


async def fetch_security_council() -> dict[str, Any]:
    """
    Fetch current Security Council membership.
    
    Returns:
        dict with:
        - permanent_members: list of 5 permanent member countries
        - non_permanent_members: list of dicts with country name and term end year
    """
    from playwright.async_api import async_playwright
    
    url = "https://www.un.org/securitycouncil/content/current-members"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                locale='en-US'
            )
            page = await context.new_page()
            await page.goto(url, wait_until='networkidle')
            
            body = await page.query_selector('body')
            all_text = await body.inner_text()
            
            # Parse permanent members - they are listed explicitly
            permanent = []
            # The format is: "Five permanent members: China, France, Russian Federation, the United Kingdom, and the United States"
            perm_match = re.search(
                r'Five permanent members:\s*(China|France|Russian Federation|United Kingdom|United States|the United Kingdom|the United States)(?:,\s*|\s+and\s+)',
                all_text
            )
            
            # Extract permanent members more carefully
            perm_section = re.search(
                r'Five permanent members:\s*([^,]+(?:,\s*[^,]+){0,3})\s*(?:,\s*and|and)\s*([^,]+?)(?:,|ten)',
                all_text
            )
            
            if perm_section:
                perm_text = perm_section.group(1) + ', ' + perm_section.group(2)
                # Clean up the text
                perm_text = re.sub(r'\s+', ' ', perm_text)
                # Split by comma
                parts = perm_text.split(',')
                for part in parts:
                    part = part.strip()
                    # Remove 'and' prefix
                    part = re.sub(r'^and\s+', '', part)
                    # Remove 'the' prefix
                    part = re.sub(r'^the\s+', '', part)
                    if part in ['China', 'France', 'Russian Federation', 'United Kingdom', 'United States']:
                        permanent.append(part)
            
            # If parsing failed, use known list
            if len(permanent) != 5:
                permanent = ['China', 'France', 'Russian Federation', 'United Kingdom', 'United States']
            
            # Parse non-permanent members
            non_permanent = []
            # Pattern: Country (Year) - extract from the list after permanent members
            np_pattern = r'([A-Z][A-Za-z\s]+?)\s*\((\d{4})\)'
            np_matches = re.findall(np_pattern, all_text)
            
            for country, year in np_matches:
                country = country.strip()
                # Filter out non-countries and duplicates
                if country and len(country) > 2 and country not in ['The Council', 'General Assembly', 'Member States']:
                    # Check if already in list
                    if not any(np['country'] == country for np in non_permanent):
                        non_permanent.append({
                            'country': country,
                            'term_end_year': int(year)
                        })
            
            return {
                'total_members': 15,
                'permanent_members': permanent,
                'non_permanent_members': non_permanent,
                'source_url': url
            }
        finally:
            await browser.close()


async def fetch_icj_judges() -> dict[str, Any]:
    """
    Fetch current International Court of Justice judges.
    
    Returns:
        dict with list of judges containing name, country, role, and membership info
    """
    from playwright.async_api import async_playwright
    
    url = "https://www.icj-cij.org/en/current-members"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                locale='en-US'
            )
            page = await context.new_page()
            await page.goto(url, wait_until='networkidle')
            
            body = await page.query_selector('body')
            all_text = await body.inner_text()
            
            judges = []
            
            # Parse President - format: "President NAME\nCountry\n\nMember since..."
            pres_match = re.search(
                r'President\s+([A-Z][A-Za-z\s]+?)\n([A-Za-z][A-Za-z\s]+?)\n\nMember of the Court since\s*([^.\n]+)',
                all_text
            )
            if pres_match:
                judges.append({
                    'name': pres_match.group(1).strip(),
                    'country': pres_match.group(2).strip(),
                    'role': 'President',
                    'member_since': pres_match.group(3).strip()
                })
            
            # Parse Vice-President
            vp_match = re.search(
                r'Vice-President\s+([A-Z][A-Za-z\s]+?)\n([A-Za-z][A-Za-z\s]+?)\n\nMember of the Court since\s*([^.\n]+)',
                all_text
            )
            if vp_match:
                judges.append({
                    'name': vp_match.group(1).strip(),
                    'country': vp_match.group(2).strip(),
                    'role': 'Vice-President',
                    'member_since': vp_match.group(3).strip()
                })
            
            # Parse regular judges - format: "Judge NAME\nCountry\n\nMember since..."
            judge_pattern = r'Judge\s+([A-Z][A-Za-z\s]+?)\n([A-Za-z][A-Za-z\s]+?)\n\nMember of the Court since\s*([^.\n]+)'
            judge_matches = re.findall(judge_pattern, all_text)
            
            for name, country, since in judge_matches:
                name = name.strip()
                country = country.strip()
                # Skip if already added as President or VP
                if not any(j['name'] == name for j in judges):
                    judges.append({
                        'name': name,
                        'country': country,
                        'role': 'Judge',
                        'member_since': since.strip()
                    })
            
            return {
                'total_judges': len(judges),
                'judges': judges,
                'source_url': url
            }
        finally:
            await browser.close()


async def fetch_organ_membership_overview() -> dict[str, Any]:
    """
    Fetch overview of UN organ memberships with links to detailed pages.
    
    Returns:
        dict with membership info for each principal UN organ
    """
    url = "https://www.un.org/en/about-us/membership-of-principal-un-organs"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            follow_redirects=True
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        organs = {}
        
        # Find all h2 headings for organs
        h2s = soup.find_all('h2')
        
        for h2 in h2s:
            organ_name = h2.get_text(strip=True)
            
            if organ_name not in ['General Assembly', 'Security Council', 
                                  'Economic and Social Council', 
                                  'Trusteeship Council', 'International Court of Justice']:
                continue
            
            # Get content after this h2 until next h2
            content_parts = []
            sibling = h2.find_next_sibling()
            
            while sibling and sibling.name != 'h2':
                if sibling.name == 'p':
                    text = sibling.get_text(strip=True)
                    if text:
                        content_parts.append(text)
                sibling = sibling.find_next_sibling()
            
            organs[organ_name] = {
                'description': content_parts[0] if content_parts else None,
                'details': content_parts
            }
        
        return {
            'organs': organs,
            'source_url': url,
            'note': 'Use get_security_council or get_icj_judges for detailed membership lists'
        }


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute UN data retrieval functions.
    
    Args:
        params: Must contain 'function' key with one of:
            - get_member_states: List all UN member states with admission dates
            - get_security_council: Current Security Council members
            - get_icj_judges: Current ICJ judges
            - get_organ_overview: Overview of all principal UN organs

    
    Returns:
        dict with 'success', 'data' or 'error' keys
    """
    function = params.get('function')
    
    if not function:
        return {
            'success': False,
            'error': 'Missing required parameter: function'
        }
    
    try:
        if function == 'get_member_states':
            data = await fetch_member_states()
            return {'success': True, 'data': data}
        
        elif function == 'get_security_council':
            data = await fetch_security_council()
            return {'success': True, 'data': data}
        
        elif function == 'get_icj_judges':
            data = await fetch_icj_judges()
            return {'success': True, 'data': data}
        
        elif function == 'get_organ_overview':
            data = await fetch_organ_membership_overview()
            return {'success': True, 'data': data}
        
        else:
            return {
                'success': False,
                'error': f'Unknown function: {function}. Valid functions: get_member_states, get_security_council, get_icj_judges, get_organ_overview'
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': f'Error executing {function}: {str(e)}'
        }


# For testing
if __name__ == '__main__':
    import json
    
    async def test():
        print("Testing get_member_states...")
        result = await execute({'function': 'get_member_states'})
        print(f"Success: {result.get('success')}")
        if result.get('success'):
            print(f"Count: {result['data']['count']}")
            print(f"First 3: {result['data']['members'][:3]}")
        else:
            print(f"Error: {result.get('error')}")
        
        print("\n" + "="*60)
        print("Testing get_security_council...")
        result = await execute({'function': 'get_security_council'})
        print(f"Success: {result.get('success')}")
        if result.get('success'):
            print(json.dumps(result['data'], indent=2))
        else:
            print(f"Error: {result.get('error')}")
        
        print("\n" + "="*60)
        print("Testing get_icj_judges...")
        result = await execute({'function': 'get_icj_judges'})
        print(f"Success: {result.get('success')}")
        if result.get('success'):
            print(f"Total judges: {result['data']['total_judges']}")
            for judge in result['data']['judges'][:5]:
                print(f"  {judge}")
        else:
            print(f"Error: {result.get('error')}")
        
        print("\n" + "="*60)
        print("Testing get_organ_overview...")
        result = await execute({'function': 'get_organ_overview'})
        print(f"Success: {result.get('success')}")
        if result.get('success'):
            print(f"Organs: {list(result['data']['organs'].keys())}")
        else:
            print(f"Error: {result.get('error')}")
    
    asyncio.run(test())