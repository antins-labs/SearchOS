"""
Shanghai Ranking GRAS (Global Ranking of Academic Subjects) Access Skill

This skill extracts ranking data from ShanghaiRanking's GRAS rankings.
The data is server-side rendered via Nuxt.js and made available in window.__NUXT__.

Supported rankings:
- GRAS: Global Ranking of Academic Subjects (世界一流学科排名)

Years: 2017-2025
Subjects: 55 subjects across 5 categories (Science, Engineering, Life Sciences, Medicine, Social Sciences)
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


# Subject categories and codes
SUBJECT_CATEGORIES = {
    "AS01": "理学 (Natural Sciences)",
    "AS02": "工学 (Engineering)",
    "AS03": "生命科学 (Life Sciences)",
    "AS04": "医学 (Medical Sciences)",
    "AS05": "社会科学 (Social Sciences)",
}

# Subject name mappings
SUBJECT_NAMES = {
    "AS0101": "数学 (Mathematics)",
    "AS0102": "物理学 (Physics)",
    "AS0103": "化学 (Chemistry)",
    "AS0104": "地球科学 (Earth Sciences)",
    "AS0105": "地理学 (Geography)",
    "AS0106": "生态学 (Ecology)",
    "AS0107": "海洋科学 (Oceanography)",
    "AS0108": "大气科学 (Atmospheric Science)",
    "AS0201": "机械工程 (Mechanical Engineering)",
    "AS0202": "电力电子工程 (Electrical & Electronic Engineering)",
    "AS0205": "控制科学与工程 (Control Science & Engineering)",
    "AS0206": "通信工程 (Telecommunication Engineering)",
    "AS0207": "仪器科学 (Instrument Science & Technology)",
    "AS0208": "生物医学工程 (Biomedical Engineering)",
    "AS0210": "计算机科学与工程 (Computer Science & Engineering)",
    "AS0211": "土木工程 (Civil Engineering)",
    "AS0212": "化学工程 (Chemical Engineering)",
    "AS0213": "材料科学与工程 (Materials Science & Engineering)",
    "AS0214": "纳米科学与技术 (Nanoscience & Nanotechnology)",
    "AS0215": "能源科学与工程 (Energy Science & Engineering)",
    "AS0216": "环境科学与工程 (Environmental Science & Engineering)",
    "AS0217": "水资源工程 (Water Resources Engineering)",
    "AS0218": "食品科学与工程 (Food Science & Technology)",
    "AS0219": "生物工程 (Biotechnology)",
    "AS0220": "生物工程 (Biological Engineering)",
    "AS0221": "航空航天工程 (Aerospace Engineering)",
    "AS0222": "船舶与海洋工程 (Marine/Ocean Engineering)",
    "AS0223": "交通运输工程 (Transportation Science & Technology)",
    "AS0224": "遥感技术 (Remote Sensing)",
    "AS0225": "矿业工程 (Mining & Mineral Engineering)",
    "AS0226": "冶金工程 (Metallurgical Engineering)",
    "AS0301": "生物学 (Biological Sciences)",
    "AS0302": "基础医学 (Basic Medical Sciences)",
    "AS0303": "农学 (Agricultural Sciences)",
    "AS0304": "兽医学 (Veterinary Sciences)",
    "AS0401": "临床医学 (Clinical Medicine)",
    "AS0402": "公共卫生 (Public Health)",
    "AS0403": "口腔医学 (Stomatology)",
    "AS0404": "护理学 (Nursing)",
    "AS0405": "医学技术 (Medical Technology)",
    "AS0406": "药学 (Pharmaceutical Sciences)",
    "AS0501": "经济学 (Economics)",
    "AS0502": "统计学 (Statistics)",
    "AS0503": "法学 (Law)",
    "AS0504": "政治学 (Political Sciences)",
    "AS0505": "社会学 (Sociology)",
    "AS0506": "教育学 (Education)",
    "AS0507": "新闻传播学 (Communication)",
    "AS0508": "心理学 (Psychology)",
    "AS0509": "工商管理 (Business Administration)",
    "AS0510": "金融学 (Finance)",
    "AS0511": "管理学 (Management)",
    "AS0512": "公共管理 (Public Administration)",
    "AS0513": "旅游管理 (Tourism Management)",
    "AS0514": "图书馆与信息管理 (Library & Information Science)",
}


class ShanghaiRankingGRASClient:
    """Client for accessing Shanghai Ranking GRAS data."""
    
    BASE_URL = "https://www.shanghairanking.cn"
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def close(self):
        """Close browser resources."""
        if self.browser:
            await self.browser.close()
            self.browser = None
    
    async def _ensure_browser(self):
        """Ensure browser is initialized."""
        if not self.browser:
            playwright = await async_playwright().start()
            self.browser = await playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
    
    async def _fetch_page_data(self, url: str) -> Optional[Dict]:
        """Fetch and extract NUXT data from a page."""
        await self._ensure_browser()
        
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Extract window.__NUXT__ data
            nuxt_data = await page.evaluate("""
                () => {
                    const nuxt = window.__NUXT__;
                    if (!nuxt) return null;
                    return JSON.parse(JSON.stringify(nuxt));
                }
            """)
            
            return nuxt_data
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
        finally:
            await page.close()
    
    async def list_subjects(self, year: int = 2024) -> Dict[str, Any]:
        """
        List all available subjects for GRAS ranking.
        
        Args:
            year: Ranking year (2017-2025)
        
        Returns:
            Dict with subject categories and subjects
        """
        url = f"{self.BASE_URL}/rankings/gras/{year}"
        
        nuxt_data = await self._fetch_page_data(url)
        
        if not nuxt_data:
            return {
                "success": False,
                "error": "Failed to fetch page data",
                "url": url
            }
        
        try:
            data = nuxt_data.get('data', [{}])[0]
            
            subjects = []
            if 'subjData' in data:
                for category in data['subjData']:
                    cat_code = category.get('code', '')
                    cat_name = category.get('nameCn', '')
                    
                    for subj in category.get('subjs', []):
                        subjects.append({
                            "code": subj.get('code'),
                            "name_cn": subj.get('nameCn'),
                            "name_en": subj.get('nameEn', ''),
                            "category_code": cat_code,
                            "category_name": cat_name,
                            "available_years": subj.get('years', [])
                        })
            
            years = []
            if 'yearList' in data:
                years = [y.get('value') for y in data['yearList']]
            
            return {
                "success": True,
                "year": year,
                "total_subjects": len(subjects),
                "subjects": subjects,
                "available_years": years,
                "url": url
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to parse data: {str(e)}",
                "url": url
            }
    
    async def get_ranking(
        self,
        subject_code: str,
        year: int = 2024,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get ranking data for a specific subject.
        
        Args:
            subject_code: Subject code (e.g., "AS0220" for Biological Engineering)
            year: Ranking year (2017-2025)
            limit: Maximum number of universities to return (None for all)
        
        Returns:
            Dict with ranking data
        """
        url = f"{self.BASE_URL}/rankings/gras/{year}/{subject_code}"
        
        nuxt_data = await self._fetch_page_data(url)
        
        if not nuxt_data:
            return {
                "success": False,
                "error": "Failed to fetch page data",
                "url": url
            }
        
        try:
            data = nuxt_data.get('data', [{}])[0]
            
            # Extract university ranking data
            universities = []
            if 'univData' in data:
                for u in data['univData']:
                    uni_data = {
                        "rank": u.get('ranking'),
                        "university_code": u.get('univCode'),
                        "name_cn": u.get('univNameCn'),
                        "name_en": u.get('univNameEn'),
                        "region": u.get('region'),
                        "score": u.get('score'),
                        "indicators": u.get('indData', {}),
                        "logo": u.get('univLogo'),
                        "inbound": u.get('inbound', False)
                    }
                    universities.append(uni_data)
            
            # Get indicator info
            indicators = []
            if 'indList' in data:
                for ind in data['indList']:
                    indicators.append({
                        "id": ind.get('id'),
                        "name_cn": ind.get('nameCn'),
                        "name_en": ind.get('nameEn'),
                        "weight": ind.get('weight')
                    })
            
            # Get region info
            regions = []
            if 'regionList' in data:
                for r in data['regionList']:
                    regions.append({
                        "code": r.get('code'),
                        "name": r.get('nameCn'),
                        "name_en": r.get('nameEn')
                    })
            
            result = {
                "success": True,
                "year": year,
                "subject_code": subject_code,
                "subject_name_cn": data.get('subjName'),
                "subject_name_en": SUBJECT_NAMES.get(subject_code, '').split('(')[1].rstrip(')') if subject_code in SUBJECT_NAMES else '',
                "category": data.get('subjCategory', {}).get('nameCn'),
                "category_code": data.get('categoryCode'),
                "total_universities": len(universities),
                "universities": universities[:limit] if limit else universities,
                "indicators": indicators,
                "regions": regions,
                "url": url
            }
            
            if limit:
                result["returned_count"] = len(result["universities"])
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to parse ranking data: {str(e)}",
                "url": url
            }
    
    async def search_universities(
        self,
        keyword: str,
        year: int = 2024,
        subject_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search for universities by name in the rankings.
        
        Args:
            keyword: Search keyword (university name)
            year: Ranking year
            subject_code: Optional subject code to limit search
        
        Returns:
            Dict with matching universities
        """
        import asyncio
        
        if subject_code:
            # Search in specific subject
            result = await self.get_ranking(subject_code, year)
            if not result.get('success'):
                return result
            
            universities = result.get('universities', [])
            matches = [
                u for u in universities
                if keyword.lower() in u.get('name_cn', '').lower() or
                   keyword.lower() in u.get('name_en', '').lower()
            ]
            
            return {
                "success": True,
                "keyword": keyword,
                "year": year,
                "subject_code": subject_code,
                "matches": len(matches),
                "universities": matches
            }
        else:
            # Search across all subjects
            subjects_result = await self.list_subjects(year)
            if not subjects_result.get('success'):
                return subjects_result
            
            all_matches = []
            subjects = subjects_result.get('subjects', [])
            
            for subj in subjects:
                try:
                    ranking = await self.get_ranking(subj['code'], year)
                    if ranking.get('success'):
                        for u in ranking.get('universities', []):
                            if keyword.lower() in u.get('name_cn', '').lower() or \
                               keyword.lower() in u.get('name_en', '').lower():
                                u['subject_code'] = subj['code']
                                u['subject_name_cn'] = subj['name_cn']
                                all_matches.append(u)
                    
                    # Small delay between requests
                    await asyncio.sleep(0.3)
                except Exception:
                    continue
            
            return {
                "success": True,
                "keyword": keyword,
                "year": year,
                "matches": len(all_matches),
                "universities": all_matches
            }


async def execute(params: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """
    Execute Shanghai Ranking GRAS skill functions.
    
    Functions:
        - list_subjects: List all available subjects for GRAS
        - get_ranking: Get ranking data for a specific subject
        - search_universities: Search for universities by name
    
    Args:
        params: Dict containing:
            - function: One of "list_subjects", "get_ranking", "search_universities"
            - year: Ranking year (default: 2024)
            - subject_code: Subject code for get_ranking (e.g., "AS0220")
            - keyword: Search keyword for search_universities
            - limit: Max results to return
    
    Returns:
        Dict with results or error information
    """
    func = params.get('function')
    
    if not func:
        return {
            "success": False,
            "error": "Missing required parameter: function",
            "valid_functions": ["list_subjects", "get_ranking", "search_universities"]
        }
    
    year = params.get('year', 2024)
    
    async with ShanghaiRankingGRASClient() as client:
        if func == "list_subjects":
            return await client.list_subjects(year)
        
        elif func == "get_ranking":
            subject_code = params.get('subject_code')
            if not subject_code:
                return {
                    "success": False,
                    "error": "Missing required parameter: subject_code",
                    "hint": "Use list_subjects to get available subject codes"
                }
            
            limit = params.get('limit')
            return await client.get_ranking(subject_code, year, limit)
        
        elif func == "search_universities":
            keyword = params.get('keyword')
            if not keyword:
                return {
                    "success": False,
                    "error": "Missing required parameter: keyword"
                }
            
            subject_code = params.get('subject_code')
            return await client.search_universities(keyword, year, subject_code)
        
        else:
            return {
                "success": False,
                "error": f"Unknown function: {func}",
                "valid_functions": ["list_subjects", "get_ranking", "search_universities"]
            }


# For testing
if __name__ == "__main__":
    import sys
    
    async def test():
        print("="*80)
        print("Testing list_subjects")
        print("="*80)
        result = await execute({"function": "list_subjects", "year": 2024})
        print(f"Success: {result.get('success')}")
        print(f"Total subjects: {result.get('total_subjects')}")
        if result.get('subjects'):
            print(f"First 5 subjects: {result['subjects'][:5]}")
        
        print("\n" + "="*80)
        print("Testing get_ranking")
        print("="*80)
        result = await execute({
            "function": "get_ranking",
            "subject_code": "AS0220",
            "year": 2024,
            "limit": 10
        })
        print(f"Success: {result.get('success')}")
        print(f"Subject: {result.get('subject_name_cn')}")
        print(f"Total universities: {result.get('total_universities')}")
        if result.get('universities'):
            print("\nTop 5 universities:")
            for u in result['universities'][:5]:
                print(f"  {u['rank']}: {u['name_cn']} ({u.get('region', 'N/A')}) - Score: {u.get('score')}")
        
        print("\n" + "="*80)
        print("Testing search_universities")
        print("="*80)
        result = await execute({
            "function": "search_universities",
            "keyword": "清华",
            "year": 2024,
            "subject_code": "AS0220"
        })
        print(f"Success: {result.get('success')}")
        print(f"Matches: {result.get('matches')}")
        if result.get('universities'):
            print("\nMatching universities:")
            for u in result['universities']:
                print(f"  {u['rank']}: {u['name_cn']}")
    
    asyncio.run(test())