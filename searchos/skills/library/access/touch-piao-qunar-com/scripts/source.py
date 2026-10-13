"""
Qunar Scenic Area Ticket Scraper
Extracts scenic area ticket information from touch.piao.qunar.com
"""

import re
import json
from typing import Any
import httpx


async def fetch_scenic_detail(sight_id: str) -> dict[str, Any]:
    """
    Fetch scenic area detail from Qunar mobile site.
    
    Args:
        sight_id: The scenic area ID (e.g., "8606")
    
    Returns:
        Dictionary containing scenic area details including title, score, tickets, etc.
    """
    url = f"https://touch.piao.qunar.com/touch/detail.htm?id={sight_id}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                return {
                    'error': f'HTTP {response.status_code}',
                    'sightId': sight_id,
                    'success': False
                }
            
            html = response.text
            data = {
                'sightId': sight_id,
                'url': url,
                'success': True
            }
            
            # Extract title and level
            title_match = re.search(r'<div class="mp-headfeagure-title"[^>]*>([^<]+)', html)
            if title_match:
                title = title_match.group(1).strip()
                # Extract scenic level (AAAAA景区, AAAA景区, etc.)
                level_match = re.search(r'\(([A]+景区)\)', title)
                if level_match:
                    data['level'] = level_match.group(1)
                    title = re.sub(r'\s*\([A]+景区\)', '', title)
                data['title'] = title
            
            # Extract score (rating)
            score_match = re.search(r'<span class="mp-commentcard-score">([^<]+)</span>', html)
            if score_match:
                score_str = score_match.group(1).strip()
                try:
                    data['score'] = float(score_str)
                except ValueError:
                    data['score'] = score_str
            
            # Extract score text (很棒, etc.)
            score_text_match = re.search(r'<span class="mp-commentcard-desc">([^<]+)</span>', html)
            if score_text_match:
                score_text = score_text_match.group(1).strip()
                if score_text:
                    data['scoreText'] = score_text
            
            # Extract comment count
            comment_match = re.search(r'<span class="mp-totalcommentnum">([^<]+)</span>', html)
            if comment_match:
                comment_text = comment_match.group(1).strip()
                # Extract number from text like "326条评论"
                num_match = re.search(r'(\d+)', comment_text)
                if num_match:
                    data['commentCount'] = int(num_match.group(1))
            
            # Extract image count
            img_count_match = re.search(r'<em class="mp-imgswipeicon-number">([^<]+)</em>', html)
            if img_count_match:
                data['imageCount'] = int(img_count_match.group(1).strip())
            
            # Extract main image
            img_match = re.search(r'<img class="mp-headfigure-img"[^>]*src="([^"]+)"', html)
            if img_match:
                img_url = img_match.group(1)
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                data['image'] = img_url
            
            # Extract ticket categories with prices
            ticket_pattern = r'<div class="mp-ticket-list[^"]*"[^>]*data-typeid="(\d+)"[^>]*>.*?<h5 class="mp-ticket-type-name[^"]*"[^>]*>([^<]+)</h5>.*?<em class="mp-price-num">([^<]+)</em>'
            
            tickets = re.findall(ticket_pattern, html, re.DOTALL)
            if tickets:
                data['ticketCategories'] = []
                prices = []
                
                for typeid, name, price in tickets:
                    name = name.strip()
                    price_str = '¥' + price.strip()
                    
                    data['ticketCategories'].append({
                        'name': name,
                        'priceFrom': price_str,
                        'typeId': typeid
                    })
                    
                    # Extract numeric price for lowest price calculation
                    price_num_match = re.search(r'([\d.]+)', price)
                    if price_num_match:
                        try:
                            prices.append(float(price_num_match.group(1)))
                        except ValueError:
                            pass
                
                # Calculate lowest and highest prices
                if prices:
                    data['lowestPrice'] = min(prices)
                    data['highestPrice'] = max(prices)
                    data['priceRange'] = f"¥{min(prices):.0f}-{max(prices):.0f}"
            
            # Try to extract description from meta tag
            desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', html)
            if desc_match:
                data['description'] = desc_match.group(1).strip()
            
            # Check if page exists (has valid content)
            if not data.get('title'):
                data['error'] = 'Scenic area not found or page unavailable'
                data['success'] = False
            
            return data
            
    except httpx.TimeoutException:
        return {
            'error': 'Request timeout',
            'sightId': sight_id,
            'success': False
        }
    except Exception as e:
        return {
            'error': str(e),
            'sightId': sight_id,
            'success': False
        }


async def search_scenic_by_id(sight_id: str) -> dict[str, Any]:
    """
    Search for a scenic area by ID and return structured data.
    
    Args:
        sight_id: The scenic area ID
    
    Returns:
        Structured scenic area data
    """
    result = await fetch_scenic_detail(sight_id)
    
    if result.get('success'):
        # Add formatted display text
        lines = []
        
        title = result.get('title', 'Unknown')
        level = result.get('level', '')
        if level:
            lines.append(f"【{title}】({level})")
        else:
            lines.append(f"【{title}】")
        
        if result.get('score'):
            score_text = result.get('scoreText', '')
            score_line = f"评分: {result['score']}"
            if score_text:
                score_line += f" ({score_text})"
            lines.append(score_line)
        
        if result.get('commentCount'):
            lines.append(f"评论数: {result['commentCount']}条")
        
        if result.get('lowestPrice'):
            price_range = result.get('priceRange')
            if price_range:
                lines.append(f"门票价格: {price_range}")
            else:
                lowest = result.get('lowestPrice', 0)
                lines.append(f"门票价格: ¥{lowest}起")
        
        lines.append(f"图片数量: {result.get('imageCount', 0)}张")
        
        if result.get('ticketCategories'):
            lines.append(f"\n票种({len(result['ticketCategories'])}种):")
            for i, ticket in enumerate(result['ticketCategories'][:10], 1):
                lines.append(f"  {i}. {ticket['name']}: {ticket['priceFrom']}")
            if len(result['ticketCategories']) > 10:
                lines.append(f"  ... 还有{len(result['ticketCategories']) - 10}种票型")
        
        result['displayText'] = '\n'.join(lines)
    
    return result


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Main entry point for the Qunar scenic area scraper.
    
    Args:
        params: Dictionary containing:
            - function: 'get_detail' or 'search' (required)
            - sightId: The scenic area ID (required for get_detail)
            - sightIds: List of scenic area IDs (optional for batch queries)
        ctx: Context object (unused but required by interface)
    
    Returns:
        Dictionary with structure:
        {
            'success': bool,
            'data': dict or list,
            'error': str (if failed),
            'displayText': str (formatted summary)
        }
    """
    function = params.get('function', 'get_detail')
    
    if function == 'get_detail':
        sight_id = params.get('sightId')
        if not sight_id:
            return {
                'success': False,
                'error': 'Missing required parameter: sightId',
                'data': None
            }
        
        # Ensure sight_id is string
        sight_id = str(sight_id)
        result = await search_scenic_by_id(sight_id)
        
        return {
            'success': result.get('success', False),
            'data': result if result.get('success') else None,
            'error': result.get('error'),
            'displayText': result.get('displayText')
        }
    
    elif function == 'batch':
        sight_ids = params.get('sightIds', [])
        if not sight_ids:
            return {
                'success': False,
                'error': 'Missing required parameter: sightIds',
                'data': None
            }
        
        results = []
        for sid in sight_ids:
            sid = str(sid)
            result = await fetch_scenic_detail(sid)
            results.append(result)
        
        # Generate summary
        success_count = sum(1 for r in results if r.get('success'))
        summary = f"成功获取 {success_count}/{len(sight_ids)} 个景区信息"
        
        return {
            'success': True,
            'data': results,
            'displayText': summary
        }
    
    else:
        return {
            'success': False,
            'error': f'Unknown function: {function}. Supported: get_detail, batch',
            'data': None
        }


# For testing
if __name__ == '__main__':
    import asyncio
    
    async def test():
        # Test single query
        print("Testing single query...")
        result = await execute({'function': 'get_detail', 'sightId': '8606'})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Test batch query
        print("\n" + "="*80)
        print("Testing batch query...")
        result = await execute({
            'function': 'batch',
            'sightIds': ['8606', '472314', '9805']
        })
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    asyncio.run(test())