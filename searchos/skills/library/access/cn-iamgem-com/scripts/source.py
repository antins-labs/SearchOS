"""
G.E.M.邓紫棋 Official Website Access Skill
Extracts tours, music albums, songs, and videos from cn.iamgem.com

Site uses WordPress with REST API for music/videos content and 
dynamic loading for tour dates.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import aiohttp


class GemSiteAccessor:
    """Access G.E.M. official website data."""
    
    BASE_URL = "https://cn.iamgem.com"
    API_URL = "https://cn.iamgem.com/wp-json/wp/v2"
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/html, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
    
    async def close(self):
        """Close the session."""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def fetch_json(self, url: str, params: Optional[Dict] = None) -> Any:
        """Fetch JSON from URL."""
        await self._ensure_session()
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            return None
    
    async def fetch_html(self, url: str) -> Optional[str]:
        """Fetch HTML from URL."""
        await self._ensure_session()
        try:
            async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception as e:
            return None
    
    async def get_tours(self) -> Dict[str, Any]:
        """
        Extract tour dates from the tours page.
        
        Returns:
            Dict with 'success', 'tours' list, or 'error' message.
        """
        html = await self.fetch_html(f"{self.BASE_URL}/tours/")
        if not html:
            return {"success": False, "error": "Failed to fetch tours page"}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Get all text from the page
        all_text = soup.get_text(separator='\n')
        lines = [line.strip() for line in all_text.split('\n') if line.strip()]
        
        # Parse tour dates
        tours = []
        current_tour = None
        seen_tours = set()  # For deduplication
        
        # Keywords for navigation items to skip
        skip_keywords = {'Music', 'Video', 'Tour', 'Shop', 'Fan Club', '搜索', '简', '繁', 'LOAD', 'I AM GLORIA'}
        
        for i, line in enumerate(lines):
            # Skip navigation and other non-content items
            if line in skip_keywords or len(line) < 3:
                continue
            
            # Check if this line contains a date (format: 2025/12/26 or 2025年12月)
            date_match = re.search(r'20[0-9]{2}[/\-年][0-9]{1,2}[/\-月][0-9]{1,2}', line)
            
            if date_match:
                # Start a new tour entry
                if current_tour and current_tour.get('dates'):
                    # Create a key for deduplication
                    tour_key = (current_tour['dates'], current_tour.get('venue', ''))
                    if tour_key not in seen_tours:
                        seen_tours.add(tour_key)
                        tours.append(current_tour)
                
                # Extract the date portion
                date_str = date_match.group(0)
                
                # Get the full date line (might include additional dates)
                date_line = line
                
                # Try to extract location and venue from the following lines
                location = ''
                venue = ''
                
                # Look ahead for venue/location information
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_line = lines[j].strip()
                    
                    # Skip if it's another date line or navigation
                    if re.search(r'20[0-9]{2}[/\-]', next_line) or next_line in skip_keywords:
                        break
                    
                    # Check for venue keywords
                    if any(keyword in next_line for keyword in ['体育场', '体育馆', '中心', '馆', '园', 'Stadium', 'Arena', 'Center']):
                        venue = next_line
                        break
                    # Otherwise might be location (short, typically city name)
                    elif len(next_line) < 15 and not location:
                        location = next_line
                
                current_tour = {
                    'dates': date_line,
                    'location': location,
                    'venue': venue
                }
            
            # Also check for venue in current tour context
            elif current_tour and not current_tour.get('venue'):
                if any(keyword in line for keyword in ['体育场', '体育馆', '中心', '园', '场', 'Stadium', 'Arena']):
                    current_tour['venue'] = line
        
        # Don't forget the last tour
        if current_tour and current_tour.get('dates'):
            tour_key = (current_tour['dates'], current_tour.get('venue', ''))
            if tour_key not in seen_tours:
                tours.append(current_tour)
        
        # Clean up tour entries
        for tour in tours:
            # Clean up dates - remove extra whitespace
            tour['dates'] = re.sub(r'\s+', ' ', tour['dates']).strip()
            # Extract city from venue if location not set
            if not tour['location'] and tour['venue']:
                # Common city names in Chinese venues
                cities = ['广州', '三亚', '福州', '徐州', '成都', '香港', '洛阳', '河北', '北京', '上海', 
                         '深圳', '武汉', '长沙', '南京', '杭州', '重庆', '天津', '西安', '苏州']
                for city in cities:
                    if city in tour['venue']:
                        tour['location'] = city
                        break
        
        return {
            "success": True,
            "count": len(tours),
            "tours": tours
        }
    
    async def get_categories(self) -> Dict[str, Any]:
        """
        Get all music album categories.
        
        Returns:
            Dict with 'success', 'categories' list, or 'error' message.
        """
        categories = await self.fetch_json(f"{self.API_URL}/categories", params={"per_page": 100})
        
        if not categories:
            return {"success": False, "error": "Failed to fetch categories"}
        
        # Handle both list and dict responses
        if isinstance(categories, dict) and 'code' in categories:
            return {"success": False, "error": categories.get('message', 'Unknown error')}
        
        result = []
        for cat in categories:
            result.append({
                'id': cat.get('id'),
                'name': cat.get('name'),
                'slug': cat.get('slug'),
                'description': cat.get('description', ''),
                'count': cat.get('count', 0),
                'link': cat.get('link')
            })
        
        return {
            "success": True,
            "count": len(result),
            "categories": result
        }
    
    async def get_posts(
        self,
        category_id: Optional[int] = None,
        per_page: int = 100,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Get posts (songs/tracks/videos).
        
        Args:
            category_id: Optional category ID to filter by album.
            per_page: Number of posts per page (max 100).
            page: Page number.
        
        Returns:
            Dict with 'success', 'posts' list, and pagination info.
        """
        params = {
            "per_page": min(per_page, 100),
            "page": page,
            "_embed": "true"
        }
        
        if category_id:
            params["categories"] = category_id
        
        posts = await self.fetch_json(f"{self.API_URL}/posts", params=params)
        
        if not posts:
            return {"success": False, "error": "Failed to fetch posts"}
        
        if isinstance(posts, dict) and 'code' in posts:
            return {"success": False, "error": posts.get('message', 'Unknown error')}
        
        result = []
        for post in posts:
            post_data = {
                'id': post.get('id'),
                'title': post.get('title', {}).get('rendered', ''),
                'link': post.get('link'),
                'date': post.get('date'),
                'modified': post.get('modified'),
                'slug': post.get('slug'),
                'content': post.get('content', {}).get('rendered', ''),
                'excerpt': post.get('excerpt', {}).get('rendered', ''),
                'categories': post.get('categories', []),
                'tags': post.get('tags', [])
            }
            
            # Extract featured image if available
            if '_embedded' in post:
                embedded = post['_embedded']
                if 'wp:featuredmedia' in embedded and embedded['wp:featuredmedia']:
                    media = embedded['wp:featuredmedia'][0]
                    post_data['featured_image'] = {
                        'url': media.get('source_url'),
                        'alt': media.get('alt_text', ''),
                        'width': media.get('media_details', {}).get('width'),
                        'height': media.get('media_details', {}).get('height')
                    }
            
            # Clean HTML from content
            if post_data['content']:
                soup = BeautifulSoup(post_data['content'], 'html.parser')
                post_data['content_text'] = soup.get_text(separator=' ', strip=True)
            
            if post_data['excerpt']:
                soup = BeautifulSoup(post_data['excerpt'], 'html.parser')
                post_data['excerpt_text'] = soup.get_text(separator=' ', strip=True)
            
            result.append(post_data)
        
        return {
            "success": True,
            "count": len(result),
            "page": page,
            "per_page": per_page,
            "posts": result
        }
    
    async def get_post(self, post_id: int) -> Dict[str, Any]:
        """
        Get a single post by ID.
        
        Args:
            post_id: The post ID.
        
        Returns:
            Dict with 'success', 'post' data, or 'error' message.
        """
        post = await self.fetch_json(f"{self.API_URL}/posts/{post_id}", params={"_embed": "true"})
        
        if not post:
            return {"success": False, "error": "Post not found"}
        
        if isinstance(post, dict) and 'code' in post:
            return {"success": False, "error": post.get('message', 'Unknown error')}
        
        # Extract embedded data
        result = {
            'id': post.get('id'),
            'title': post.get('title', {}).get('rendered', ''),
            'link': post.get('link'),
            'date': post.get('date'),
            'modified': post.get('modified'),
            'slug': post.get('slug'),
            'content': post.get('content', {}).get('rendered', ''),
            'excerpt': post.get('excerpt', {}).get('rendered', ''),
            'categories': post.get('categories', []),
            'tags': post.get('tags', [])
        }
        
        # Extract featured image
        if '_embedded' in post:
            embedded = post['_embedded']
            
            if 'wp:featuredmedia' in embedded and embedded['wp:featuredmedia']:
                media = embedded['wp:featuredmedia'][0]
                result['featured_image'] = {
                    'url': media.get('source_url'),
                    'alt': media.get('alt_text', ''),
                    'width': media.get('media_details', {}).get('width'),
                    'height': media.get('media_details', {}).get('height')
                }
            
            # Get category names
            if 'wp:term' in embedded:
                for terms in embedded['wp:term']:
                    for term in terms:
                        if term.get('taxonomy') == 'category':
                            result['category_names'] = result.get('category_names', [])
                            result['category_names'].append(term.get('name'))
        
        # Clean HTML from content
        if result['content']:
            soup = BeautifulSoup(result['content'], 'html.parser')
            result['content_text'] = soup.get_text(separator=' ', strip=True)
            
            # Extract any video embeds from content
            iframes = soup.find_all('iframe')
            if iframes:
                result['videos'] = [iframe.get('src') for iframe in iframes if iframe.get('src')]
        
        if result['excerpt']:
            soup = BeautifulSoup(result['excerpt'], 'html.parser')
            result['excerpt_text'] = soup.get_text(separator=' ', strip=True)
        
        return {
            "success": True,
            "post": result
        }
    
    async def get_albums(self) -> Dict[str, Any]:
        """
        Get all music albums (categories with posts).
        
        Returns:
            Dict with 'success', 'albums' list, or 'error' message.
        """
        # Get categories
        cats_result = await self.get_categories()
        if not cats_result.get('success'):
            return cats_result
        
        # Get posts count for each category
        albums = []
        for cat in cats_result['categories']:
            if cat['count'] > 0:  # Only include categories with posts
                albums.append({
                    'id': cat['id'],
                    'name': cat['name'],
                    'slug': cat['slug'],
                    'description': cat['description'],
                    'track_count': cat['count'],
                    'link': cat['link']
                })
        
        # Sort by ID to get a consistent order
        albums.sort(key=lambda x: x['id'])
        
        return {
            "success": True,
            "count": len(albums),
            "albums": albums
        }
    
    async def get_album_tracks(self, album_id: int) -> Dict[str, Any]:
        """
        Get all tracks in an album.
        
        Args:
            album_id: The album (category) ID.
        
        Returns:
            Dict with 'success', 'tracks' list, or 'error' message.
        """
        # Get category info
        category = await self.fetch_json(f"{self.API_URL}/categories/{album_id}")
        
        if not category or (isinstance(category, dict) and 'code' in category):
            return {"success": False, "error": "Album not found"}
        
        # Get posts in this category
        posts_result = await self.get_posts(category_id=album_id, per_page=100)
        if not posts_result.get('success'):
            return posts_result
        
        return {
            "success": True,
            "album": {
                'id': category.get('id'),
                'name': category.get('name'),
                'description': category.get('description', ''),
                'link': category.get('link')
            },
            "track_count": len(posts_result['posts']),
            "tracks": posts_result['posts']
        }
    
    async def search_posts(self, query: str, per_page: int = 20) -> Dict[str, Any]:
        """
        Search for posts by keyword.
        
        Args:
            query: Search keyword.
            per_page: Number of results per page.
        
        Returns:
            Dict with 'success', 'results' list, or 'error' message.
        """
        params = {
            "search": query,
            "per_page": min(per_page, 100),
            "_embed": "true"
        }
        
        posts = await self.fetch_json(f"{self.API_URL}/posts", params=params)
        
        if not posts:
            return {"success": False, "error": "Search failed"}
        
        if isinstance(posts, dict) and 'code' in posts:
            return {"success": False, "error": posts.get('message', 'Unknown error')}
        
        result = []
        for post in posts:
            result.append({
                'id': post.get('id'),
                'title': post.get('title', {}).get('rendered', ''),
                'link': post.get('link'),
                'date': post.get('date'),
                'excerpt': BeautifulSoup(post.get('excerpt', {}).get('rendered', ''), 'html.parser').get_text(strip=True)
            })
        
        return {
            "success": True,
            "query": query,
            "count": len(result),
            "results": result
        }
    
    async def get_videos_page(self) -> Dict[str, Any]:
        """
        Get video content from the videos page.
        
        Returns:
            Dict with 'success', 'videos' list, or 'error' message.
        """
        html = await self.fetch_html(f"{self.BASE_URL}/videos/")
        if not html:
            return {"success": False, "error": "Failed to fetch videos page"}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        videos = []
        
        # Extract video information from the page text
        text_content = soup.get_text(separator='\n')
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
        
        # Parse video entries
        # Format: date line, then title line
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Skip navigation items
            if line in ['Music', 'Video', 'Tour', 'Shop', 'Fan Club', '搜索', '简', '繁', 'LOAD', 'Watch']:
                i += 1
                continue
            
            # Check for date pattern (e.g., "May 27 2025")
            date_match = re.match(r'^([A-Za-z]+\s+\d{1,2}\s+\d{4})$', line)
            if date_match:
                # Next line should be the video title
                if i + 1 < len(lines):
                    title = lines[i + 1]
                    # Skip if it's a navigation item or copyright
                    if title not in ['Music', 'Video', 'Tour', 'Shop', 'Fan Club', 'LOAD'] and \
                       'Copyright' not in title and 'rights reserved' not in title:
                        
                        video_data = {
                            'date': date_match.group(1),
                            'title': title
                        }
                        
                        # Try to extract chapter number
                        chapter_match = re.search(r'第(\d+)章', title)
                        if chapter_match:
                            video_data['chapter'] = int(chapter_match.group(1))
                        
                        videos.append(video_data)
                        i += 2
                        continue
            
            i += 1
        
        # Find embedded videos (Bilibili, YouTube, etc.)
        iframes = soup.find_all('iframe', src=re.compile(r'bilibili|youtube|vimeo|youku'))
        embed_urls = [iframe.get('src') for iframe in iframes if iframe.get('src')]
        
        return {
            "success": True,
            "count": len(videos),
            "videos": videos,
            "embedded_videos": embed_urls
        }


# Global accessor instance
_accessor = None


async def get_accessor() -> GemSiteAccessor:
    """Get or create the global accessor instance."""
    global _accessor
    if _accessor is None:
        _accessor = GemSiteAccessor()
    return _accessor


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Main entry point for the G.E.M. website access skill.
    
    Args:
        params: Dict containing:
            - function: The function to call. Must be one of:
                - get_tours: Get tour dates
                - get_albums: Get all albums/categories
                - get_album_tracks: Get tracks in an album (requires album_id)
                - get_posts: Get all posts (optional: category_id, per_page, page)
                - get_post: Get a single post (requires post_id)
                - get_categories: Get all categories
                - search: Search posts (requires query)
                - get_videos: Get video page content
            - Additional parameters based on the function.
        ctx: Optional context (not used).
    
    Returns:
        Dict with 'success' and data or 'error'.
    """
    if 'function' not in params:
        return {
            "success": False,
            "error": "Missing required parameter: function"
        }
    
    function = params['function']
    accessor = await get_accessor()
    
    try:
        if function == 'get_tours':
            return await accessor.get_tours()
        
        elif function == 'get_albums':
            return await accessor.get_albums()
        
        elif function == 'get_album_tracks':
            if 'album_id' not in params:
                return {"success": False, "error": "Missing required parameter: album_id"}
            return await accessor.get_album_tracks(params['album_id'])
        
        elif function == 'get_posts':
            return await accessor.get_posts(
                category_id=params.get('category_id'),
                per_page=params.get('per_page', 100),
                page=params.get('page', 1)
            )
        
        elif function == 'get_post':
            if 'post_id' not in params:
                return {"success": False, "error": "Missing required parameter: post_id"}
            return await accessor.get_post(params['post_id'])
        
        elif function == 'get_categories':
            return await accessor.get_categories()
        
        elif function == 'search':
            if 'query' not in params:
                return {"success": False, "error": "Missing required parameter: query"}
            return await accessor.search_posts(params['query'], params.get('per_page', 20))
        
        elif function == 'get_videos':
            return await accessor.get_videos_page()
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {function}. "
                        f"Valid functions: get_tours, get_albums, get_album_tracks, "
                        f"get_posts, get_post, get_categories, search, get_videos"
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Error executing {function}: {str(e)}"
        }
    finally:
        # Don't close the session here, let it be reused
        pass