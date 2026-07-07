"""
Japan Ministry of Defense (MOD) - Defense Ministers Access Skill

Fetches information about current and previous defense ministers,
vice-ministers, and parliamentary vice-ministers from the Japan MOD website.
"""

import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from typing import Any, Dict, List, Optional
from datetime import datetime


class MODJapanFetcher:
    """Fetches Japan Ministry of Defense minister information"""
    
    BASE_URL_JA = 'https://www.mod.go.jp/j/profile/minister/index.html'
    BASE_URL_EN = 'https://www.mod.go.jp/en/about/previous_ministers.html'
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }
    
    async def fetch_page(self, session: aiohttp.ClientSession, url: str) -> str:
        """Fetch page HTML with error handling"""
        try:
            async with session.get(url, headers=self.HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()
                return await response.text()
        except Exception as e:
            raise Exception(f"Failed to fetch {url}: {str(e)}")
    
    def parse_japanese_name(self, text: str) -> Dict[str, str]:
        """
        Parse Japanese name with reading
        Example: "小泉　進次郎（こいずみ　しんじろう）"
        Returns: {"name": "小泉　進次郎", "reading": "こいずみ　しんじろう"}
        """
        match = re.match(r'([^\(（]+)[\(（]([^\)）]+)[\)）]', text.strip())
        if match:
            return {
                "name": match.group(1).strip(),
                "reading": match.group(2).strip()
            }
        return {"name": text.strip(), "reading": ""}
    
    def parse_japanese_date_range(self, text: str) -> Dict[str, str]:
        """
        Parse Japanese date range
        Example: "令和6年10月1日～令和7年10月21日"
        Returns: {"start": "...", "end": "..."}
        """
        parts = text.split('～')
        if len(parts) == 2:
            return {
                "start": parts[0].strip(),
                "end": parts[1].strip()
            }
        elif len(parts) == 1 and '～' in text:
            return {
                "start": parts[0].strip(),
                "end": "present"
            }
        return {"start": text.strip(), "end": ""}
    
    def parse_english_name(self, text: str) -> Dict[str, str]:
        """
        Parse English name
        Example: "Mr. NAKATANI Gen"
        Returns: {"title": "Mr.", "name": "NAKATANI Gen"}
        """
        match = re.match(r'(Mr\.|Ms\.)\s+(.+)', text.strip())
        if match:
            return {
                "title": match.group(1),
                "name": match.group(2).strip()
            }
        return {"title": "", "name": text.strip()}
    
    def parse_english_date_range(self, text: str) -> Dict[str, str]:
        """
        Parse English date range
        Example: "October 2024 to October 2025"
        Returns: {"start": "October 2024", "end": "October 2025"}
        """
        parts = text.split(' to ')
        if len(parts) == 2:
            return {
                "start": parts[0].strip(),
                "end": parts[1].strip()
            }
        return {"start": text.strip(), "end": ""}
    
    async def get_current_ministers_ja(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """
        Extract current ministers from Japanese page
        Returns current Minister, Vice-Minister, and Parliamentary Vice-Ministers
        """
        html = await self.fetch_page(session, self.BASE_URL_JA)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            "language": "ja",
            "url": self.BASE_URL_JA,
            "retrieved_at": datetime.now().isoformat(),
            "current_minister": None,
            "current_vice_minister": None,
            "current_parliamentary_vice_ministers": []
        }
        
        # Extract current defense minister (防衛大臣)
        # The structure is: h2 followed by div.flex-side-column.center with minister info
        minister_heading = soup.find('h2', string='防衛大臣')
        if minister_heading:
            next_div = minister_heading.find_next_sibling('div', class_='flex-side-column')
            if next_div:
                text = next_div.get_text(separator='\n', strip=True)
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                # Parse the lines:
                # Line 0: "防衛大臣"
                # Line 1: "小泉　進次郎（こいずみ　しんじろう）"
                # Line 2: "【在任期間】2025（令和7）年10月21日～"
                # Line 3: "プロフィール"
                
                if len(lines) >= 2:
                    # Line 1 should be the name
                    name_line = lines[1] if lines[0] == '防衛大臣' else lines[0]
                    name_info = self.parse_japanese_name(name_line)
                    
                    # Line 2 should be the term
                    term = ""
                    if len(lines) >= 3:
                        term_match = re.search(r'【在任期間】(.+)', lines[2])
                        if term_match:
                            term = term_match.group(1).strip()
                    
                    # Find profile link
                    profile_link = next_div.find('a', href=True)
                    profile_url = profile_link.get('href') if profile_link else None
                    
                    result["current_minister"] = {
                        "name": name_info["name"],
                        "reading": name_info["reading"],
                        "position": "防衛大臣 (Minister of Defense)",
                        "term": term,
                        "profile_url": profile_url
                    }
        
        # Extract current vice-minister (防衛副大臣)
        # Structure: h2 in a column-03-item div, followed by <figure> with name
        vice_heading = soup.find('h2', string='防衛副大臣')
        if vice_heading:
            next_figure = vice_heading.find_next_sibling('figure')
            if next_figure:
                fig_text = next_figure.get_text(separator='\n', strip=True)
                lines = [l.strip() for l in fig_text.split('\n') if l.strip()]
                
                if lines:
                    name_info = self.parse_japanese_name(lines[0])
                    
                    profile_link = next_figure.find('a', href=True)
                    profile_url = profile_link.get('href') if profile_link else None
                    
                    result["current_vice_minister"] = {
                        "name": name_info["name"],
                        "reading": name_info["reading"],
                        "position": "防衛副大臣 (Vice Minister of Defense)",
                        "profile_url": profile_url
                    }
        
        # Extract current parliamentary vice-ministers (政務官)
        parliamentary_headings = soup.find_all('h2', string='政務官')
        for heading in parliamentary_headings:
            next_figure = heading.find_next_sibling('figure')
            if next_figure:
                fig_text = next_figure.get_text(separator='\n', strip=True)
                lines = [l.strip() for l in fig_text.split('\n') if l.strip()]
                
                if lines:
                    name_info = self.parse_japanese_name(lines[0])
                    
                    profile_link = next_figure.find('a', href=True)
                    profile_url = profile_link.get('href') if profile_link else None
                    
                    result["current_parliamentary_vice_ministers"].append({
                        "name": name_info["name"],
                        "reading": name_info["reading"],
                        "position": "政務官 (Parliamentary Vice-Minister of Defense)",
                        "profile_url": profile_url
                    })
        
        return result
    
    async def get_previous_ministers_ja(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Extract list of previous ministers from Japanese page"""
        html = await self.fetch_page(session, self.BASE_URL_JA)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            "language": "ja",
            "url": self.BASE_URL_JA,
            "retrieved_at": datetime.now().isoformat(),
            "previous_ministers": [],
            "previous_vice_ministers": [],
            "previous_parliamentary_vice_ministers": [],
            "previous_assistant_ministers": []
        }
        
        tables = soup.find_all('table')
        
        for table in tables:
            prev_heading = table.find_previous(['h2', 'h3'])
            heading_text = prev_heading.get_text(strip=True) if prev_heading else ''
            
            category = None
            if '歴代防衛大臣' in heading_text and '政務官' not in heading_text and '副大臣' not in heading_text:
                category = 'previous_ministers'
            elif '歴代防衛副大臣' in heading_text:
                category = 'previous_vice_ministers'
            elif '歴代防衛大臣政務官' in heading_text:
                category = 'previous_parliamentary_vice_ministers'
            elif '歴代防衛大臣補佐官' in heading_text:
                category = 'previous_assistant_ministers'
            
            if not category:
                continue
            
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    name_text = cells[0].get_text(strip=True)
                    term_text = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                    
                    if name_text:
                        name_info = self.parse_japanese_name(name_text)
                        date_range = self.parse_japanese_date_range(term_text)
                        
                        activity_link = cells[-1].find('a', href=True)
                        activity_url = activity_link.get('href') if activity_link else None
                        
                        result[category].append({
                            "name": name_info["name"],
                            "reading": name_info["reading"],
                            "term_start": date_range["start"],
                            "term_end": date_range["end"],
                            "activity_url": activity_url
                        })
        
        return result
    
    async def get_previous_ministers_en(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Extract list of previous ministers from English page"""
        html = await self.fetch_page(session, self.BASE_URL_EN)
        soup = BeautifulSoup(html, 'html.parser')
        
        result = {
            "language": "en",
            "url": self.BASE_URL_EN,
            "retrieved_at": datetime.now().isoformat(),
            "ministers_of_defense": [],
            "state_ministers": [],
            "parliamentary_vice_ministers": []
        }
        
        h1 = soup.find('h1', string='Previous Ministers')
        if not h1:
            return result
        
        content_area = h1.parent
        current_section = None
        
        for elem in content_area.find_all(['h2', 'p']):
            if elem.name == 'h2':
                section_title = elem.get_text(strip=True)
                if 'Ministers of Defense' in section_title and 'State' not in section_title:
                    current_section = 'ministers_of_defense'
                elif 'State Ministers' in section_title:
                    current_section = 'state_ministers'
                elif 'Parliamentary Vice' in section_title:
                    current_section = 'parliamentary_vice_ministers'
            elif elem.name == 'p' and current_section:
                text = elem.get_text(strip=True)
                
                match = re.match(r'(Mr\.\s+.+?)([A-Z][a-z]+\s+\d{4}\s+to\s+.+)', text)
                if match:
                    name_part = match.group(1).strip()
                    date_part = match.group(2).strip()
                    
                    name_info = self.parse_english_name(name_part)
                    date_range = self.parse_english_date_range(date_part)
                    
                    result[current_section].append({
                        "name": name_info["name"],
                        "title": name_info["title"],
                        "term_start": date_range["start"],
                        "term_end": date_range["end"]
                    })
        
        return result
    
    async def get_profile(self, session: aiohttp.ClientSession, url: str) -> Dict[str, Any]:
        """
        Fetch and parse individual profile from kantei.go.jp
        """
        try:
            html = await self.fetch_page(session, url)
            soup = BeautifulSoup(html, 'html.parser')
            
            result = {
                "url": url,
                "retrieved_at": datetime.now().isoformat(),
                "name": None,
                "reading": None,
                "position": None,
                "birth_date": None,
                "birth_place": None,
                "biography": []
            }
            
            body = soup.find('body')
            if body:
                text = body.get_text(separator='\n', strip=True)
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                
                # Find position
                for i, line in enumerate(lines):
                    if '防衛大臣' in line and len(line) < 20:
                        result["position"] = line
                        if i >= 2:
                            result["name"] = lines[i-2]
                            result["reading"] = lines[i-1]
                        break
                
                # Find birth date
                for i, line in enumerate(lines):
                    if '生年月日' in line:
                        if i + 1 < len(lines):
                            result["birth_date"] = lines[i + 1]
                        break
                
                # Find birth place
                for i, line in enumerate(lines):
                    if '出身地' in line:
                        if i + 1 < len(lines):
                            result["birth_place"] = lines[i + 1]
                        break
                
                # Extract biography
                bio_start = False
                for line in lines:
                    if 'これまでの経歴' in line or '略歴' in line:
                        bio_start = True
                        continue
                    if bio_start:
                        if re.match(r'[０-９\d]+年', line) or re.match(r'[平成|令和|昭和].+年', line):
                            result["biography"].append(line)
                        elif len(result["biography"]) > 0:
                            if not any(skip in line for skip in ['開く', '閉じる', 'ツイート', 'JavaScript']):
                                result["biography"].append(line)
            
            return result
            
        except Exception as e:
            return {
                "url": url,
                "error": str(e)
            }


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """
    Execute function for Japan MOD minister information retrieval
    
    Parameters:
        function: The function to call
            - get_current_ministers_ja: Get current ministers (Japanese)
            - get_previous_ministers_ja: Get previous ministers list (Japanese)
            - get_previous_ministers_en: Get previous ministers list (English)
            - get_profile: Get individual profile by URL
        url: Profile URL (required for get_profile function)
    
    Returns:
        Dict with ministers information or error
    """
    function = params.get('function')
    
    if not function:
        return {
            "success": False,
            "error": "Missing required parameter: function"
        }
    
    fetcher = MODJapanFetcher()
    
    async with aiohttp.ClientSession() as session:
        try:
            if function == 'get_current_ministers_ja':
                result = await fetcher.get_current_ministers_ja(session)
                return {
                    "success": True,
                    "data": result
                }
            
            elif function == 'get_previous_ministers_ja':
                result = await fetcher.get_previous_ministers_ja(session)
                return {
                    "success": True,
                    "data": result
                }
            
            elif function == 'get_previous_ministers_en':
                result = await fetcher.get_previous_ministers_en(session)
                return {
                    "success": True,
                    "data": result
                }
            
            elif function == 'get_profile':
                url = params.get('url')
                if not url:
                    return {
                        "success": False,
                        "error": "Missing required parameter: url for get_profile function"
                    }
                
                result = await fetcher.get_profile(session, url)
                return {
                    "success": True,
                    "data": result
                }
            
            else:
                return {
                    "success": False,
                    "error": f"Unknown function: {function}"
                }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# For testing
if __name__ == "__main__":
    async def test():
        import json
        
        print("Testing current ministers (Japanese):")
        result = await execute({"function": "get_current_ministers_ja"})
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\nTesting previous ministers (Japanese):")
        result = await execute({"function": "get_previous_ministers_ja"})
        if result['success']:
            print(f"Found {len(result['data']['previous_ministers'])} previous ministers")
            print(f"Found {len(result['data']['previous_vice_ministers'])} vice ministers")
        
        print("\nTesting previous ministers (English):")
        result = await execute({"function": "get_previous_ministers_en"})
        if result['success']:
            print(f"Found {len(result['data']['ministers_of_defense'])} ministers")
            print(f"Found {len(result['data']['state_ministers'])} state ministers")
    
    asyncio.run(test())