"""Investing.com Historical Market Data Access Skill

This skill fetches historical market data from investing.com using browser automation
to handle Cloudflare protection and extract financial data.

Supported instruments:
- Indices: Hang Seng, S&P 500, Dow Jones, NASDAQ, Nikkei, FTSE, DAX, etc.
- Forex: EUR/USD, GBP/USD, USD/JPY, and other major pairs
- Commodities: Gold, Silver, Oil, Natural Gas, etc.
- Crypto: Bitcoin, Ethereum, and others
- Stocks: AAPL, MSFT, GOOGL, AMZN, TSLA, etc.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlencode
import hashlib

# Try to import playwright
try:
    from playwright.async_api import async_playwright, Browser, Page, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Try to import aiohttp
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False


# Instrument ID mapping (subset of commonly requested instruments)
INSTRUMENT_IDS = {
    # Indices
    'hang-sen-40': '944422', 'hsi': '944422',
    'us-30': '169', 'djia': '169', 'dow-jones': '169',
    'spx-500': '20', 'sp500': '20', 's&p-500': '20',
    'nasdaq-100': '1497', 'nasdaq': '1497',
    'nikkei-225': '178', 'nikkei': '178',
    'ftse-100': '27', 'ftse': '27', 'uk-100': '27',
    'dax': '172', 'germany-40': '172',
    'cac-40': '167', 'cac': '167',
    'euro-stoxx-50': '177', 'euro-50': '177',
    'shanghai-composite': '39218', 'shanghai': '39218',
    
    # Forex
    'eur-usd': '1', 'eurusd': '1',
    'gbp-usd': '3', 'gbpusd': '3',
    'usd-jpy': '4', 'usdjpy': '4',
    'usd-chf': '5', 'usdchf': '5',
    'aud-usd': '6', 'audusd': '6',
    'usd-cad': '7', 'usdcad': '7',
    'nzd-usd': '8', 'nzdusd': '8',
    'eur-gbp': '9', 'eurgbp': '9',
    'eur-jpy': '10', 'eurjpy': '10',
    'gbp-jpy': '11', 'gbpjpy': '11',
    
    # Commodities
    'gold': '8830', 'xauusd': '8830',
    'silver': '8836', 'xagusd': '8836',
    'crude-oil-wti': '8849', 'wti': '8849', 'oil': '8849',
    'brent-oil': '8833', 'brent': '8833',
    'natural-gas': '8862', 'ngas': '8862',
    'copper': '8831',
    'platinum': '8834',
    
    # Crypto
    'bitcoin': '945629', 'btc': '945629',
    'ethereum': '940810', 'eth': '940810',
    'ripple': '1010801', 'xrp': '1010801',
    'litecoin': '1010809', 'ltc': '1010809',
    'cardano': '1061453', 'ada': '1061453',
    'solana': '1109517', 'sol': '1109517',
    'dogecoin': '1169226', 'doge': '1169226',
    
    # Stocks
    'aapl': '6408', 'apple': '6408',
    'msft': '2456', 'microsoft': '2456',
    'googl': '6562', 'google': '6562',
    'amzn': '237', 'amazon': '237',
    'tsla': '6347', 'tesla': '6347',
    'meta': '26487', 'fb': '26487',
    'nvda': '6396', 'nvidia': '6396',
    'nflx': '23290', 'netflix': '23290',
    'amd': '252',
    'intc': '248', 'intel': '248',
    'dis': '39202', 'disney': '39202',
    
    # ETFs
    'spy': '13959',
    'qqq': '252',
    'dia': '242',
    'gld': '927',
    'slv': '935',
}

# URL slugs for building historical data URLs
URL_SLUGS = {
    'hang-sen-40': 'hang-sen-40', 'hsi': 'hang-sen-40',
    'us-30': 'us-30', 'dow-jones': 'us-30', 'djia': 'us-30',
    'spx-500': 'us-spx-500', 'sp500': 'us-spx-500', 's&p-500': 'us-spx-500',
    'nasdaq-100': 'nasdaq-100', 'nasdaq': 'nasdaq-100',
    'nikkei-225': 'nikkei-225', 'nikkei': 'nikkei-225',
    'ftse-100': 'uk-ftse-100', 'ftse': 'uk-ftse-100',
    'dax': 'germany-dax-30', 'germany-40': 'germany-dax-30',
    'cac-40': 'france-cac-40', 'cac': 'france-cac-40',
    'euro-stoxx-50': 'euro-stoxx-50',
    'shanghai-composite': 'shanghai-composite',
    'gold': 'gold', 'silver': 'silver',
    'crude-oil-wti': 'crude-oil', 'wti': 'crude-oil', 'oil': 'crude-oil',
    'brent-oil': 'brent-oil',
    'natural-gas': 'natural-gas',
    'eur-usd': 'eur-usd', 'gbp-usd': 'gbp-usd', 'usd-jpy': 'usd-jpy',
    'bitcoin': 'bitcoin', 'btc': 'bitcoin',
    'ethereum': 'ethereum', 'eth': 'ethereum',
}

# Base URL
BASE_URL = 'https://www.investing.com'

# Historical data paths by asset type
HISTORICAL_PATHS = {
    'index': '/indices/{slug}-historical-data',
    'forex': '/currencies/{slug}-historical-data',
    'commodity': '/commodities/{slug}-historical-data',
    'crypto': '/crypto/{slug}-historical-data',
    'stock': '/equities/{slug}-historical-data',
    'default': '/indices/{slug}-historical-data',
}

# Cache
_cache: dict = {}
_CACHE_TTL = 3600


def _get_asset_type(instrument: str) -> str:
    """Determine asset type from instrument name"""
    inst = instrument.lower()
    
    # Forex
    if any(x in inst for x in ['-usd', '-eur', '-gbp', '-jpy', '-chf', 'usd-', 'eur-', 'gbp-']):
        return 'forex'
    
    # Crypto
    if inst in {'bitcoin', 'btc', 'ethereum', 'eth', 'ripple', 'xrp', 'litecoin', 'ltc',
                'cardano', 'ada', 'solana', 'sol', 'dogecoin', 'doge'}:
        return 'crypto'
    
    # Commodities
    if any(x in inst for x in ['gold', 'silver', 'oil', 'brent', 'gas', 'copper', 'platinum']):
        return 'commodity'
    
    # Stocks
    if inst in {'aapl', 'msft', 'googl', 'amzn', 'tsla', 'meta', 'nvda', 'nflx', 'amd', 'intc', 'dis'}:
        return 'stock'
    
    return 'index'


def _get_cache_key(*args) -> str:
    return hashlib.md5('|'.join(str(a) for a in args).encode()).hexdigest()


def _get_cached(key: str) -> Optional[dict]:
    if key in _cache:
        entry = _cache[key]
        if datetime.now().timestamp() - entry['timestamp'] < _CACHE_TTL:
            return entry['data']
    return None


def _set_cache(key: str, data: dict):
    _cache[key] = {'data': data, 'timestamp': datetime.now().timestamp()}


class InvestingComClient:
    """Client for fetching data from investing.com using Playwright"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._playwright = None
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, *args):
        await self.close()
        
    async def close(self):
        if self.browser:
            await self.browser.close()
            self.browser = None
    
    async def init_browser(self):
        """Initialize browser with anti-detection"""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright required. Install: pip install playwright && playwright install chromium")
        
        if self.browser is None:
            self._playwright = await async_playwright().start()
            self.browser = await self._playwright.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                locale='en-US',
            )
            
            # Anti-detection script
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
            """)
    
    def resolve_instrument(self, instrument: str) -> tuple:
        """Resolve instrument to (id, slug, type)"""
        inst = instrument.lower().strip()
        
        # Numeric ID
        if instrument.isdigit():
            return (instrument, f'instrument-{instrument}', 'default')
        
        # Find ID
        inst_id = INSTRUMENT_IDS.get(inst)
        
        # Find slug
        slug = URL_SLUGS.get(inst, inst)
        
        # Get type
        asset_type = _get_asset_type(inst)
        
        return (inst_id, slug, asset_type)
    
    def build_url(self, instrument: str, start_date: str = None, end_date: str = None) -> str:
        """Build historical data URL"""
        inst_id, slug, asset_type = self.resolve_instrument(instrument)
        
        # Get path template
        path_template = HISTORICAL_PATHS.get(asset_type, HISTORICAL_PATHS['default'])
        url = f"{BASE_URL}{path_template.format(slug=slug)}"
        
        # Add dates
        params = {}
        if start_date:
            if '-' in start_date:
                parts = start_date.split('-')
                start_date = f"{parts[1]}/{parts[2]}/{parts[0]}"
            params['st_date'] = start_date
        if end_date:
            if '-' in end_date:
                parts = end_date.split('-')
                end_date = f"{parts[1]}/{parts[2]}/{parts[0]}"
            params['end_date'] = end_date
        
        if params:
            url += '?' + urlencode(params)
        
        return url
    
    async def fetch_data(self, url: str, wait: float = 15.0) -> dict:
        """Fetch page and extract data"""
        await self.init_browser()
        
        page = await self.context.new_page()
        
        try:
            await page.goto(url, timeout=90000, wait_until='domcontentloaded')
            
            # Wait for Cloudflare
            for _ in range(int(wait)):
                await asyncio.sleep(1)
                title = await page.title()
                if 'Cloudflare' not in title and 'Just a moment' not in title:
                    await asyncio.sleep(2)
                    break
            
            title = await page.title()
            if 'Cloudflare' in title or 'Just a moment' in title:
                return {'error': 'Cloudflare challenge not passed', 'title': title}
            
            # Try __NEXT_DATA__
            script = await page.query_selector('script#__NEXT_DATA__')
            if script:
                content = await script.inner_text()
                if content:
                    try:
                        data = json.loads(content)
                        return {'success': True, 'source': 'next_data', 'data': data}
                    except:
                        pass
            
            # Fallback to table
            table_data = await self._extract_table(page)
            if table_data:
                return {'success': True, 'source': 'table', 'data': table_data}
            
            return {'error': 'Could not extract data', 'title': title}
            
        except Exception as e:
            return {'error': str(e), 'error_type': type(e).__name__}
        finally:
            await page.close()
    
    async def _extract_table(self, page: Page) -> Optional[list]:
        """Extract data from HTML table"""
        selectors = [
            'table[data-test="historical-data-table"]',
            'table#historicalDataTbl',
            'table.genTbl',
            'table',
        ]
        
        for sel in selectors:
            try:
                tables = await page.query_selector_all(sel)
                for table in tables:
                    rows = await table.query_selector_all('tr')
                    if len(rows) > 2:
                        data = []
                        for row in rows[1:]:
                            cells = await row.query_selector_all('td')
                            if len(cells) >= 5:
                                vals = [(await c.inner_text()).strip() for c in cells]
                                if vals[0]:
                                    data.append({
                                        'date': vals[0],
                                        'close': vals[1] if len(vals) > 1 else '',
                                        'open': vals[2] if len(vals) > 2 else '',
                                        'high': vals[3] if len(vals) > 3 else '',
                                        'low': vals[4] if len(vals) > 4 else '',
                                        'volume': vals[5] if len(vals) > 5 else '',
                                        'change_pct': vals[6] if len(vals) > 6 else '',
                                    })
                        if len(data) >= 2:
                            return data
            except:
                continue
        return None
    
    def parse_next_data(self, data: dict) -> tuple:
        """Extract historical data from __NEXT_DATA__"""
        results = []
        metadata = {}
        
        props = data.get('props', {}).get('pageProps', {})
        
        # Get metadata
        header = props.get('instrumentHeader', {})
        if header:
            metadata['name'] = header.get('name', '')
            metadata['pair_id'] = header.get('pairId', '')
        
        # Find historical data
        def find_arrays(obj):
            found = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k.lower() in ['historical', 'historicaldata', 'pricedata', 'quotes']:
                        if isinstance(v, list):
                            found.append(v)
                        elif isinstance(v, dict) and 'data' in v:
                            found.append(v['data'])
                    found.extend(find_arrays(v))
            elif isinstance(obj, list):
                for v in obj:
                    found.extend(find_arrays(v))
            return found
        
        arrays = find_arrays(props)
        for arr in arrays:
            if isinstance(arr, list) and len(arr) > 5:
                first = arr[0] if arr else {}
                if isinstance(first, dict) and any(k in str(first).lower() for k in ['date', 'price', 'close']):
                    results.extend(arr)
        
        return results, metadata


async def get_historical_data(instrument: str, start_date: str = None, end_date: str = None, **kwargs) -> dict:
    """Fetch historical price data"""
    cache_key = _get_cache_key('hist', instrument, start_date, end_date)
    
    cached = _get_cached(cache_key)
    if cached:
        return {**cached, 'from_cache': True}
    
    async with InvestingComClient() as client:
        inst_id, slug, asset_type = client.resolve_instrument(instrument)
        url = client.build_url(instrument, start_date, end_date)
        
        result = await client.fetch_data(url)
        
        if result.get('error'):
            return {
                'success': False,
                'error': result['error'],
                'url': url,
                'instrument_id': inst_id,
                'instrument_slug': slug,
                'asset_type': asset_type,
            }
        
        if result.get('source') == 'next_data':
            hist, meta = client.parse_next_data(result['data'])
            response = {
                'success': True,
                'data': hist,
                'instrument_id': inst_id or meta.get('pair_id'),
                'instrument_name': meta.get('name', slug.upper()),
                'instrument_slug': slug,
                'asset_type': asset_type,
                'source': 'next_data',
                'url': url,
                'metadata': meta,
            }
        else:
            response = {
                'success': True,
                'data': result.get('data', []),
                'instrument_id': inst_id,
                'instrument_name': slug.upper(),
                'instrument_slug': slug,
                'asset_type': asset_type,
                'source': 'table_extraction',
                'url': url,
            }
        
        if response.get('success'):
            _set_cache(cache_key, response)
        
        return response


async def search_instrument(query: str, **kwargs) -> dict:
    """Search for instruments"""
    q = query.lower().strip()
    matches = []
    
    for key, val in INSTRUMENT_IDS.items():
        if q in key:
            matches.append({
                'slug': key,
                'instrument_id': val,
                'match_type': 'exact' if q == key else 'partial',
            })
    
    return {'success': True, 'query': query, 'results': matches, 'total': len(matches)}


async def list_supported_instruments(**kwargs) -> dict:
    """List all supported instruments"""
    categories = {
        'indices': ['hang-sen-40', 'us-30', 'spx-500', 'nasdaq-100', 'nikkei-225', 
                    'ftse-100', 'dax', 'cac-40', 'euro-stoxx-50', 'shanghai-composite'],
        'forex': ['eur-usd', 'gbp-usd', 'usd-jpy', 'usd-chf', 'aud-usd', 
                  'usd-cad', 'nzd-usd', 'eur-gbp', 'eur-jpy', 'gbp-jpy'],
        'commodities': ['gold', 'silver', 'crude-oil-wti', 'brent-oil', 'natural-gas', 'copper', 'platinum'],
        'crypto': ['bitcoin', 'ethereum', 'ripple', 'litecoin', 'cardano', 'solana', 'dogecoin'],
        'stocks': ['aapl', 'msft', 'googl', 'amzn', 'tsla', 'meta', 'nvda', 'nflx', 'amd', 'intc'],
    }
    
    grouped = {}
    for cat, keys in categories.items():
        grouped[cat] = [{'slug': k, 'instrument_id': INSTRUMENT_IDS.get(k)} for k in keys if k in INSTRUMENT_IDS]
    
    return {'success': True, 'instruments': grouped, 'total': len(INSTRUMENT_IDS)}


async def execute(params: dict[str, Any], ctx: Any = None) -> dict[str, Any]:
    """Main entry point"""
    function = params.get('function', '')
    
    try:
        if function == 'get_historical_data':
            return await get_historical_data(
                instrument=params.get('instrument', ''),
                start_date=params.get('start_date'),
                end_date=params.get('end_date'),
            )
        elif function == 'search_instrument':
            return await search_instrument(query=params.get('query', ''))
        elif function == 'list_supported_instruments':
            return await list_supported_instruments()
        else:
            return {
                'success': False,
                'error': f"Unknown function: {function}",
                'available_functions': ['get_historical_data', 'search_instrument', 'list_supported_instruments'],
            }
    except Exception as e:
        return {'success': False, 'error': str(e), 'error_type': type(e).__name__}


if __name__ == '__main__':
    async def test():
        result = await execute({'function': 'list_supported_instruments'})
        print(f"Instruments: {result['total']}")
        
        result = await execute({'function': 'search_instrument', 'query': 'gold'})
        print(f"Search: {result}")
    
    asyncio.run(test())