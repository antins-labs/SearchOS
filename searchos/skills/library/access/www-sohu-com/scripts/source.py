"""
Sohu Article Fetcher - SearchOS Access Skill

Fetches article content and extracts rankings from Sohu.com travel ranking articles.
Supports extracting "Top N" lists and individual rank mentions from article text.
"""

import httpx
import asyncio
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
import json


async def fetch_article(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Fetch and parse a Sohu article page.
    
    Args:
        params: Must contain 'url' (full article URL) or 'article_id' (article ID)
        ctx: Optional context (unused)
    
    Returns:
        Article metadata, content, and extracted rankings
    """
    url = params.get('url')
    article_id = params.get('article_id')
    media_id = params.get('media_id')
    extract_rankings = params.get('extract_rankings', True)
    
    # Construct URL if only article_id provided
    if not url and article_id:
        if media_id:
            url = f"https://www.sohu.com/a/{article_id}_{media_id}"
        else:
            url = f"https://www.sohu.com/a/{article_id}"
    
    if not url:
        return {"error": "Missing required parameter: url or article_id", "success": False}
    
    # Validate URL
    if 'sohu.com' not in url:
        return {"error": "URL must be from sohu.com domain", "success": False}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                return {"error": f"HTTP {response.status_code}", "success": False, "url": url}
            
            html = response.text
            final_url = str(response.url)
            
            # Extract basic metadata
            title_match = re.search(r'<title>([^<]+)</title>', html)
            title = title_match.group(1).strip() if title_match else None
            
            # H1 title (usually cleaner)
            h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
            h1_title = h1_match.group(1).strip() if h1_match else None
            
            # Extract article ID and media ID from URL
            id_match = re.search(r'/a/(\d+)_(\d+)', final_url)
            fetched_article_id = id_match.group(1) if id_match else None
            fetched_media_id = id_match.group(2) if id_match else None
            
            # Extract publish time
            time_match = re.search(r'class=["\']time["\'][^>]*>\s*([^<]+?)\s*</span>', html)
            if not time_match:
                time_match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', html)
            if not time_match:
                time_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', html)
            publish_time = time_match.group(1).strip() if time_match else None
            
            # Extract author/source
            author_match = re.search(r'class=["\']name["\'][^>]*>([^<]+)</span>', html)
            author = author_match.group(1).strip() if author_match else None
            
            # Extract meta description
            desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html)
            description = desc_match.group(1) if desc_match else None
            
            # Extract article content
            article_match = re.search(r'<article[^>]*id="mp-editor"[^>]*>(.*?)</article>', html, re.DOTALL)
            if not article_match:
                article_match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
            
            content_paragraphs = []
            content = None
            if article_match:
                article_html = article_match.group(1)
                paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', article_html, re.DOTALL)
                for p in paragraphs:
                    text = re.sub(r'<[^>]+>', '', p).strip()
                    text = re.sub(r'&nbsp;', ' ', text)
                    text = re.sub(r'&[a-z]+;', '', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    if text and len(text) > 5:
                        content_paragraphs.append(text)
                content = '\n\n'.join(content_paragraphs)
            
            # Extract rankings if requested
            rankings = None
            if extract_rankings and content:
                rankings = extract_rankings_from_content(content)
            
            return {
                "success": True,
                "url": final_url,
                "article_id": fetched_article_id,
                "media_id": fetched_media_id,
                "title": h1_title or title,
                "author": author,
                "publish_time": publish_time,
                "description": description,
                "content": content,
                "content_length": len(content) if content else 0,
                "paragraph_count": len(content_paragraphs),
                "rankings": rankings
            }
            
    except httpx.TimeoutException:
        return {"error": "Request timeout", "success": False, "url": url}
    except Exception as e:
        return {"error": str(e), "success": False, "url": url}


def extract_rankings_from_content(content: str) -> Optional[List[Dict[str, Any]]]:
    """
    Extract ranking/list items from article content.
    
    Looks for patterns like:
    - "排名前十的...分别为A、B、C" (top N list)
    - "排名第X名的XX景区" (rank mentions)
    - "XX景区排名第三" (reverse rank mention)
    - Numbered lists
    """
    rankings = []
    
    # Pattern 1: "排名前十...分别为A、B、C" (Chinese numeral "十" for 10)
    chinese_ten_match = re.search(r'排名前十(?:的)?([^为]*?)为([^。]+)', content)
    if chinese_ten_match:
        items_str = chinese_ten_match.group(2)
        items = re.split(r'[、，,]', items_str)
        items = [item.strip() for item in items if item.strip() and len(item.strip()) > 1]
        if items:
            rankings.append({
                "type": "top_n_list",
                "n": 10,
                "title": "Top 10",
                "items": items[:30]
            })
    
    # Pattern 2: "排名前X的...分别为..." (Arabic numerals)
    if not any(r['type'] == 'top_n_list' for r in rankings):
        top_n_match = re.search(r'排名前(\d+)(?:的)?[^为]*?为([^。]+)', content)
        if top_n_match:
            n = int(top_n_match.group(1))
            items_str = top_n_match.group(2)
            items = re.split(r'[、，,]', items_str)
            items = [item.strip() for item in items if item.strip() and len(item.strip()) > 1]
            if items:
                rankings.append({
                    "type": "top_n_list",
                    "n": n,
                    "title": f"Top {n}",
                    "items": items[:30]
                })
    
    # Pattern 3: Individual rank mentions - "排名第X[名位]"
    rank_dict = {}
    
    # Find all rank mentions with Arabic numerals
    for match in re.finditer(r'排名第?(\d+)[名位]', content):
        try:
            rank = int(match.group(1))
            if 1 <= rank <= 100:
                # Get text after the rank mention
                start = match.end()
                context = content[start:start+60]
                # Try to find a scenic spot name
                name_match = re.search(r'^的?([^。，\n]{2,30}?(?:景区|旅游区?|湖|岛|瀑布|公园|湿地|山|寺|院|园))', context)
                if name_match:
                    name = name_match.group(1).strip()
                    if name.startswith('的'):
                        name = name[1:]
                    # Clean up common suffixes
                    name = re.sub(r'(?:景区|旅游区|风景名胜区)$', '', name).strip()
                    if rank not in rank_dict and len(name) >= 2:
                        rank_dict[rank] = name
        except ValueError:
            continue
    
    # Pattern 4: Chinese numeral ranks "第一名", "第二名", etc.
    chinese_nums = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, 
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15,
        '十六': 16, '十七': 17, '十八': 18, '十九': 19, '二十': 20
    }
    
    for cn_num, num in chinese_nums.items():
        if num not in rank_dict:
            # Pattern: "第X名的XX景区" or "获得第X名的是XX景区"
            cn_match = re.search(f'第{cn_num}名[^。\\n]{{0,15}}([^。\\n]{{2,30}}(?:景区|旅游|湖|岛|瀑布|公园|山|湿地))', content)
            if cn_match:
                name = cn_match.group(1).strip()
                name = re.sub(r'^(?:的是|为)', '', name).strip()
                name = re.sub(r'(?:景区|旅游区)$', '', name).strip()
                if len(name) >= 2:
                    rank_dict[num] = name
    
    if rank_dict:
        rankings.append({
            "type": "rank_mentions",
            "title": "提名的排名",
            "items": [{"rank": k, "name": v} for k, v in sorted(rank_dict.items())]
        })
    
    # Pattern 5: Numbered list items (paragraphs starting with numbers)
    numbered_items = re.findall(r'^\s*(\d+)[\.、．]\s*([^\n]{10,200})$', content, re.MULTILINE)
    if numbered_items and len(numbered_items) >= 3:
        rankings.append({
            "type": "numbered_list",
            "title": "编号列表",
            "items": [{"number": int(n), "text": t.strip()} for n, t in numbered_items[:50]]
        })
    
    return rankings if rankings else None


async def search_articles(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Search for Sohu articles (basic implementation).
    Note: Sohu doesn't have a public search API, so this returns a message.
    
    Args:
        params: Search parameters
        ctx: Optional context
    
    Returns:
        Search result message
    """
    return {
        "success": False,
        "error": "Sohu search is not publicly available as an API. Please provide specific article URLs.",
        "hint": "Use fetch_article with a specific URL like https://www.sohu.com/a/748417406_484968"
    }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the Sohu article fetcher skill.
    
    Args:
        params: Must contain:
            - function: 'fetch_article' or 'search_articles'
            - Additional params depend on the function
        ctx: Optional context
    
    Returns:
        Result dictionary with success/error status
    """
    function = params.get('function')
    
    if not function:
        return {"error": "Missing required parameter: function", "success": False}
    
    if function == 'fetch_article':
        return await fetch_article(params, ctx)
    elif function == 'search_articles':
        return await search_articles(params, ctx)
    else:
        return {"error": f"Unknown function: {function}", "success": False}


# For direct testing
if __name__ == "__main__":
    import asyncio
    
    async def test():
        # Test fetch_article
        result = await execute({
            "function": "fetch_article",
            "url": "https://www.sohu.com/a/748417406_484968"
        })
        print("Fetch Article Result:")
        print(f"  Title: {result.get('title')}")
        print(f"  Publish Time: {result.get('publish_time')}")
        print(f"  Content Length: {result.get('content_length')}")
        if result.get('rankings'):
            print(f"  Rankings: {len(result['rankings'])} groups found")
            for r in result['rankings'][:2]:
                print(f"    {r['type']}: {len(r.get('items', []))} items")
    
    asyncio.run(test())