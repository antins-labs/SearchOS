"""
CPPCC (中国人民政治协商会议) Committee Members Access Skill
Fetches and parses structured committee member lists from www.cppcc.gov.cn
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any


async def execute(params: dict[str, Any], ctx=None) -> dict[str, Any]:
    """
    Execute CPPCC access skill.
    
    Args:
        params: Dictionary containing:
            - function: "get_committee_members" or "get_member_details"
            - url: (optional) Specific article URL to fetch
            - party: (optional) Filter by party/group name
            - member_name: (optional) Search for specific member (for get_member_details)

    
    Returns:
        Dictionary with structured results or error information
    """
    function = params.get("function", "")
    
    if function == "get_committee_members":
        return await get_committee_members(params)
    elif function == "get_member_details":
        return await get_member_details(params)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_committee_members", "get_member_details"]
        }


async def get_committee_members(params: dict[str, Any]) -> dict[str, Any]:
    """
    Fetch and parse committee members from CPPCC website.
    
    Args:
        params: 
            - url: (optional) Specific article URL
            - party: (optional) Filter by party/group name

    
    Returns:
        Dictionary with:
            - success: bool
            - title: Article title
            - parties: List of party/group member lists
            - total_members: Total count
            - error: (if failed) Error message
    """
    default_url = "http://www.cppcc.gov.cn/zxww/2023/01/18/ARTI1674005617470226.shtml"
    url = params.get("url") or default_url
    party_filter = params.get("party", "").strip()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: Failed to fetch page",
                        "url": url
                    }
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extract title
                title_elem = soup.find('title')
                title = title_elem.get_text(strip=True) if title_elem else "CPPCC Committee Members"
                
                # Parse committee structure
                parties = parse_committee_list(soup)
                
                if not parties:
                    return {
                        "success": False,
                        "error": "No committee member data found on page",
                        "url": url,
                        "title": title
                    }
                
                # Apply party filter if specified
                if party_filter:
                    parties = [p for p in parties if party_filter.lower() in p['party'].lower()]
                    if not parties:
                        return {
                            "success": False,
                            "error": f"No parties found matching filter: {party_filter}",
                            "url": url,
                            "title": title
                        }
                
                # Calculate totals
                total_members = sum(p['member_count'] for p in parties)
                
                # Prepare response (include full member lists)
                result_parties = []
                for p in parties:
                    result_parties.append({
                        "party": p['party'],
                        "declared_count": p.get('declared_count'),
                        "member_count": p['member_count'],
                        "members": p['members']
                    })
                
                return {
                    "success": True,
                    "url": url,
                    "title": title,
                    "parties": result_parties,
                    "party_count": len(parties),
                    "total_members": total_members
                }
    
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timeout",
            "url": url
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}",
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Parse error: {str(e)}",
            "url": url
        }


async def get_member_details(params: dict[str, Any]) -> dict[str, Any]:
    """
    Search for a specific member across all parties.
    
    Args:
        params:
            - member_name: Name to search for (required)
            - url: (optional) Specific article URL

    
    Returns:
        Dictionary with:
            - success: bool
            - member_name: Searched name
            - found: bool
            - matches: List of matches with party affiliation
            - error: (if failed) Error message
    """
    member_name = params.get("member_name", "").strip()
    
    if not member_name:
        return {
            "success": False,
            "error": "member_name parameter is required"
        }
    
    # Fetch all members
    default_url = "http://www.cppcc.gov.cn/zxww/2023/01/18/ARTI1674005617470226.shtml"
    url = params.get("url") or default_url
    fetch_params = {"url": url}
    result = await get_committee_members(fetch_params)
    
    if not result.get("success"):
        return result
    
    # Search for member
    matches = []
    for party_data in result.get("parties", []):
        party_name = party_data["party"]
        for member in party_data["members"]:
            # Check if member_name appears in the member string
            if member_name in member:
                # Parse member details
                name, attributes = parse_member_attributes(member)
                matches.append({
                    "raw_name": member,
                    "name": name,
                    "attributes": attributes,
                    "party": party_name
                })
    
    return {
        "success": True,
        "member_name": member_name,
        "found": len(matches) > 0,
        "match_count": len(matches),
        "matches": matches,
        "url": result.get("url"),
        "title": result.get("title")
    }


def parse_committee_list(soup: BeautifulSoup) -> list[dict]:
    """
    Parse the committee member list from HTML.
    
    Args:
        soup: BeautifulSoup parsed HTML
    
    Returns:
        List of dictionaries with party name and members
    """
    paragraphs = soup.find_all('p')
    
    parties = []
    current_party = None
    current_members = []
    declared_count = None
    
    # Pattern to match party headers like "中国共产党（87人）" or "中国共产党(87人)"
    party_pattern = re.compile(r'^(.+?)[（\(](\d+)人[）\)]$')
    
    for p in paragraphs:
        text = p.get_text(strip=True)
        if not text:
            continue
        
        # Check if this is a party header
        match = party_pattern.match(text)
        if match:
            # Save previous party
            if current_party and current_members:
                parties.append({
                    'party': current_party,
                    'declared_count': declared_count,
                    'member_count': len(current_members),
                    'members': current_members
                })
            
            current_party = match.group(1)
            declared_count = int(match.group(2))
            current_members = []
            continue
        
        # Skip non-member text
        if not current_party:
            continue
        
        # Check if this looks like a member list
        # Skip header/footer text
        skip_keywords = ['新华社', '政协', '会议', '通过', '版权所有', '京ICP', '技术支持']
        if any(kw in text for kw in skip_keywords):
            continue
        
        # Member lists are separated by Chinese comma (、)
        if '、' in text:
            names = [n.strip() for n in text.split('、') if n.strip()]
            current_members.extend(names)
    
    # Don't forget the last party
    if current_party and current_members:
        parties.append({
            'party': current_party,
            'declared_count': declared_count,
            'member_count': len(current_members),
            'members': current_members
        })
    
    return parties


def parse_member_attributes(member_str: str) -> tuple[str, dict]:
    """
    Parse member name and attributes from member string.
    
    Member strings can include attributes like:
    - 王宁（军队） - affiliation
    - 田向利（女） - gender
    - 巴特尔（蒙古族） - ethnicity
    - 韦建刚（壮族） - ethnicity
    - 王丽萍（女，浙江） - gender and location
    
    Args:
        member_str: Raw member string like "王宁（军队）" or "田向利（女）"
    
    Returns:
        Tuple of (clean_name, attributes_dict)
    """
    # Pattern to extract name and attributes
    match = re.match(r'^([^\(（]+)[\(（]([^）\)]+)[）\)]$', member_str)
    
    if match:
        name = match.group(1).strip()
        attrs_str = match.group(2).strip()
        
        # Parse attributes (comma-separated)
        attributes = {}
        attr_parts = [a.strip() for a in re.split(r'[，,、]', attrs_str)]
        
        for attr in attr_parts:
            if attr == '女':
                attributes['gender'] = 'female'
            elif attr == '男':
                attributes['gender'] = 'male'
            elif any(eth in attr for eth in ['族', '族']):
                attributes['ethnicity'] = attr
            else:
                # Could be affiliation, location, or other info
                if 'affiliation' not in attributes:
                    attributes['affiliation'] = attr
                else:
                    # Multiple attributes
                    if isinstance(attributes.get('affiliation'), str):
                        attributes['affiliation'] = [attributes['affiliation']]
                    attributes['affiliation'].append(attr)
        
        return name, attributes
    
    # No attributes found
    return member_str.strip(), {}


# For testing
if __name__ == "__main__":
    async def test():
        # Test get_committee_members
        print("Testing get_committee_members...")
        result = await execute({"function": "get_committee_members"})
        print(f"Success: {result.get('success')}")
        print(f"Title: {result.get('title')}")
        print(f"Party count: {result.get('party_count')}")
        print(f"Total members: {result.get('total_members')}")
        
        if result.get('success'):
            print("\nFirst 3 parties:")
            for party in result['parties'][:3]:
                print(f"  {party['party']}: {party['member_count']} members")
                print(f"    Sample: {', '.join(party['members'][:3])}")
        
        # Test get_member_details
        print("\n" + "="*50)
        print("Testing get_member_details...")
        result = await execute({"function": "get_member_details", "member_name": "王沪宁"})
        print(f"Success: {result.get('success')}")
        print(f"Found: {result.get('found')}")
        print(f"Match count: {result.get('match_count')}")
        if result.get('matches'):
            for match in result['matches']:
                print(f"  {match['name']} - {match['party']}")
                print(f"    Attributes: {match['attributes']}")
    
    asyncio.run(test())