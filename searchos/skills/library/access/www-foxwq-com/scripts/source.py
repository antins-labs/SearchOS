"""
Fox围棋(foxwq.com) News Extractor

Access skill for www.foxwq.com - a Chinese Go/Baduk news website.
Fetches news articles and article lists with direct HTTP requests.
"""

import asyncio
import re
from typing import Any
import aiohttp
from bs4 import BeautifulSoup


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute foxwq.com news extraction.
    
    Args:
        params: Dictionary containing:
            - function: "get_article", "list_news", or "get_comments"
            - article_id: Article ID for get_article/get_comments (string or int, e.g., "14371")
            - page: Page number for list_news (default: 1)
    
    Returns:
        Dictionary with article/list data or error information
    """
    function = params.get("function", "")
    
    if function == "get_article":
        return await get_article(params, ctx)
    elif function == "list_news":
        return await list_news(params, ctx)
    elif function == "get_comments":
        return await get_comments(params, ctx)
    else:
        return {
            "success": False,
            "error": f"Unknown function: {function}",
            "available_functions": ["get_article", "list_news", "get_comments"]
        }


async def get_article(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Fetch a single news article from foxwq.com.
    
    Args:
        params: Must contain "article_id"
    
    Returns:
        Article data including title, author, content, publish time, views, and related news
    """
    article_id = params.get("article_id")
    if not article_id:
        return {
            "success": False,
            "error": "Missing required parameter: article_id"
        }
    
    # Normalize article_id to string
    article_id = str(article_id).strip()
    
    url = f"https://www.foxwq.com/news/{article_id}.html"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    return {
                        "success": False,
                        "error": f"Article not found: {article_id}",
                        "status_code": 404
                    }
                
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP error: {response.status}",
                        "status_code": response.status
                    }
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extract title from h3.news-list-title
                title_el = soup.find('h3', class_='news-list-title')
                title = title_el.get_text(strip=True) if title_el else ''
                
                # Fallback to page title
                if not title and soup.title:
                    title = soup.title.get_text(strip=True).replace('-野狐围棋', '').strip()
                
                # Extract metadata from news-list-tag
                author = ''
                views = 0
                publish_time = ''
                
                tag_div = soup.find('div', class_='news-list-tag')
                if tag_div:
                    tag_text = tag_div.get_text()
                    
                    # Extract author: 作者：菜菜子
                    author_match = re.search(r'作者[：:]\s*([^\s]+)', tag_text)
                    if author_match:
                        author = author_match.group(1)
                    
                    # Extract views: 点击：11301
                    views_match = re.search(r'点击[：:]\s*(\d+)', tag_text)
                    if views_match:
                        views = int(views_match.group(1))
                    
                    # Extract publish time: 2023-06-01 19:25
                    time_match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', tag_text)
                    if time_match:
                        publish_time = time_match.group(1)
                
                # Extract content from news-list-content
                content_div = soup.find('div', class_='news-list-content')
                content = content_div.get_text(strip=True, separator='\n') if content_div else ''
                
                # Extract keywords
                keywords_meta = soup.find('meta', attrs={'name': 'Keywords'})
                keywords = keywords_meta.get('content', '') if keywords_meta else ''
                
                # Extract description
                desc_meta = soup.find('meta', attrs={'name': 'description'})
                description = desc_meta.get('content', '') if desc_meta else ''
                
                # Extract related news
                related_news = []
                related_div = soup.find('div', class_='news-list-relevance')
                if related_div:
                    for item in related_div.find_all('div', class_='news-title'):
                        related_news.append(item.get_text(strip=True))
                
                return {
                    "success": True,
                    "article": {
                        "article_id": article_id,
                        "url": url,
                        "title": title,
                        "author": author,
                        "publish_time": publish_time,
                        "views": views,
                        "keywords": keywords,
                        "description": description,
                        "content": content,
                        "content_length": len(content),
                        "related_news": related_news
                    }
                }
    
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timeout"
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


async def list_news(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Fetch a list of news articles from foxwq.com.
    
    Args:
        params: Can contain "page" (default: 1)
    
    Returns:
        List of news articles with titles, URLs, and pagination info
    """
    page = params.get("page", 1)
    try:
        page = int(page)
    except (ValueError, TypeError):
        page = 1
    
    # Construct URL based on page number
    if page == 1:
        url = "https://www.foxwq.com/news/"
    else:
        url = f"https://www.foxwq.com/news/index/p/{page}.html"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    
    timeout = aiohttp.ClientTimeout(total=30)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP error: {response.status}",
                        "status_code": response.status
                    }
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Extract news items
                news_items = []
                
                # Find all media containers (each news item)
                media_divs = soup.find_all('div', class_='media')
                
                for media in media_divs:
                    # Find the title link (h3.media-heading > a)
                    title_el = media.find('h3', class_='media-heading')
                    if not title_el:
                        continue
                    
                    link = title_el.find('a', href=True)
                    if not link or '/news/listid/id/' not in link.get('href', ''):
                        continue
                    
                    href = link.get('href')
                    title = link.get_text(strip=True)
                    
                    # Extract article ID from URL
                    # Format: /news/listid/id/16784.html
                    id_match = re.search(r'/id/(\d+)\.html', href)
                    article_id = id_match.group(1) if id_match else None
                    
                    # Try to find date in the media container
                    time_el = media.find(['span', 'time'], class_=lambda x: x and 'time' in x.lower())
                    date_text = time_el.get_text(strip=True) if time_el else ''
                    
                    # Look for date pattern in the entire media element
                    if not date_text:
                        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', media.get_text())
                        if date_match:
                            date_text = date_match.group(1)
                    
                    news_items.append({
                        "article_id": article_id,
                        "title": title,
                        "url": f"https://www.foxwq.com{href}" if href.startswith('/') else href,
                        "date": date_text
                    })
                
                # Get pagination info
                pagination = soup.find('ul', class_='pagination')
                total_pages = None
                current_page = page
                
                if pagination:
                    # Find last page link (末页 means "last page")
                    last_link = pagination.find('a', href=lambda x: x and '末页' in str(x))
                    if last_link:
                        last_href = last_link.get('href', '')
                        last_match = re.search(r'/p/(\d+)\.html', last_href)
                        if last_match:
                            total_pages = int(last_match.group(1))
                    
                    # If no 末页 link, try to find max page number
                    if total_pages is None:
                        page_numbers = []
                        for link in pagination.find_all('a', href=True):
                            text = link.get_text(strip=True)
                            href = link.get('href', '')
                            if text.isdigit():
                                page_numbers.append(int(text))
                            match = re.search(r'/p/(\d+)\.html', href)
                            if match:
                                page_numbers.append(int(match.group(1)))
                        if page_numbers:
                            total_pages = max(page_numbers)
                
                return {
                    "success": True,
                    "news_list": news_items,
                    "page": current_page,
                    "total_pages": total_pages,
                    "has_next": total_pages is not None and current_page < total_pages,
                    "has_prev": current_page > 1,
                    "count": len(news_items)
                }
    
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timeout"
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


async def get_comments(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Fetch comments for a news article.
    
    Args:
        params: Must contain "article_id", can contain "page" (default: 0)
    
    Returns:
        Comments data with count and comment list
    """
    article_id = params.get("article_id")
    if not article_id:
        return {
            "success": False,
            "error": "Missing required parameter: article_id"
        }
    
    article_id = str(article_id).strip()
    page = params.get("page", 0)
    try:
        page = int(page)
    except (ValueError, TypeError):
        page = 0
    
    # API endpoint for comments
    import random
    url = f"https://www.foxwq.com/news/ajaxGetCommentPc.html?page={page}&newsid={article_id}&random={random.random()}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'X-Requested-With': 'XMLHttpRequest',
    }
    
    timeout = aiohttp.ClientTimeout(total=15)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return {
                        "success": False,
                        "error": f"HTTP error: {response.status}",
                        "status_code": response.status
                    }
                
                data = await response.json()
                
                # Parse the HTML in 'info' field to extract comment details
                comments = []
                if 'info' in data and data['info']:
                    # The API returns HTML with comment items
                    # Extract comment count from 'data' field
                    comment_count = data.get('data', 0)
                    
                    # Parse HTML to extract individual comments
                    if isinstance(data['info'], str):
                        soup = BeautifulSoup(data['info'], 'html.parser')
                        
                        for item in soup.find_all('div', class_='comment-item'):
                            comment = {}
                            
                            # Extract username
                            name_el = item.find('div', class_='vc-item-text')
                            if name_el:
                                comment['username'] = name_el.get_text(strip=True)
                            
                            # Extract time
                            time_el = item.find('div', class_='vc-item-time')
                            if time_el:
                                comment['time'] = time_el.get_text(strip=True)
                            
                            # Extract content
                            content_el = item.find('div', class_='vc-item-content')
                            if content_el:
                                comment['content'] = content_el.get_text(strip=True)
                            
                            # Extract like count
                            like_el = item.find('span', class_='vc-item-like-count')
                            if like_el:
                                try:
                                    comment['likes'] = int(like_el.get_text(strip=True))
                                except ValueError:
                                    comment['likes'] = 0
                            
                            if comment.get('content'):
                                comments.append(comment)
                
                return {
                    "success": True,
                    "article_id": article_id,
                    "page": page,
                    "comment_count": data.get('data', 0),
                    "comments": comments,
                    "comments_fetched": len(comments)
                }
    
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Request timeout"
        }
    except aiohttp.ClientError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }