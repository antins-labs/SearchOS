"""短期本机检索接口：只输出目标站点结果，不暴露浏览器控制端口或会话。"""
from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import secrets
import time
from urllib.parse import urlencode, urlsplit

from searchos.skills.runtime.browser_auth import AuthRequired, browser_options, require_state, revoke, start_login


class XSearchBrowser:
    def __init__(self, context):
        self.context = context

    async def search(self, query: str, limit: int, mode: str) -> dict:
        url = 'https://x.com/search?' + urlencode({'q': query, 'src': 'typed_query', 'f': 'live' if mode == 'latest' else 'top'})
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=20000)
            await page.wait_for_timeout(1500)
            if any(part in urlsplit(page.url).path for part in ('/login', '/onboarding', '/i/flow')):
                raise AuthRequired('auth_required: X 登录态已失效，请在本机窗口重新登录后重试。')
            try:
                await page.wait_for_selector('article[data-testid="tweet"], [data-testid="emptyState"]', timeout=15000)
            except Exception:
                if '/login' in page.url or '/onboarding' in page.url:
                    raise AuthRequired('auth_required: X 登录态已失效。')
                raise RuntimeError('search_unavailable: X 未返回帖子或明确的空结果状态，可能存在挑战或页面变化。')
            if await page.locator('[data-testid="emptyState"]').count():
                text = await page.locator('[data-testid="emptyState"]').inner_text()
                if any(t in text.lower() for t in ('no results', '没有结果', '未找到', 'no result')):
                    return {'records': [], 'query': query, 'source_method': 'x_authenticated_browser',
                            'source_url': url, 'pagination': {'stop_reason': 'empty_match', 'complete': False}}
                raise RuntimeError('search_unavailable: X 返回了非搜索结果状态。')
            records = {}
            stop = 'budget'
            deadline = time.monotonic() + 20
            stagnant = 0
            for _ in range(8):
                # 固定宿主代码；调用方不能执行 JS、读取 cookie/storage 或任意属性。
                rows = await page.locator('article[data-testid="tweet"]').evaluate_all('''articles => articles.map(a => {
                    const t = a.querySelector('time'); const link = t && t.closest('a');
                    const text = a.querySelector('[data-testid="tweetText"]');
                    return {href: link && link.getAttribute('href'), text: text ? text.innerText : '',
                            created_at: t && t.getAttribute('datetime')};
                })''')
                before = len(records)
                for row in rows:
                    import re
                    match = re.fullmatch(r'/([A-Za-z0-9_]{1,15})/status/([0-9]+)', row.get('href') or '')
                    if not match:
                        continue
                    username, tweet_id = match.groups()
                    canonical = f'https://x.com/{username}/status/{tweet_id}'
                    records[tweet_id] = {'id': tweet_id, 'author_username': username,
                        'text': row.get('text', ''), 'created_at': row.get('created_at'),
                        'url': canonical, 'source_url': canonical, 'source_method': 'x_authenticated_browser'}
                if len(records) >= limit:
                    stop = 'limit'; break
                stagnant = stagnant + 1 if len(records) == before else 0
                if stagnant >= 2:
                    stop = 'no_growth'; break
                if time.monotonic() >= deadline:
                    break
                await page.mouse.wheel(0, 900)
                await page.wait_for_timeout(1500)
            if not records:
                raise RuntimeError('search_unavailable: 无法从页面解析有效帖子，不应当作空匹配。')
            return {'records': list(records.values())[:limit], 'query': query, 'source_url': url,
                    'source_method': 'x_authenticated_browser', 'pagination': {'stop_reason': stop, 'complete': False}}
        finally:
            await page.close()


@asynccontextmanager
async def serve_search(adapter, *, proxy_mode: str = 'inherit'):
    """令牌仅对本次命令有效；不开放 CDP、任意导航、代码执行或凭据读取。"""
    from aiohttp import web
    token = secrets.token_urlsafe(32)
    lock = asyncio.Lock()
    async def search(request):
        if request.headers.get('Origin') or not secrets.compare_digest(request.headers.get('Authorization', '').encode(), ('Bearer ' + token).encode()):
            return web.json_response({'error': 'unauthorized'}, status=403)
        try:
            args = await request.json()
            if not isinstance(args, dict) or set(args) - {'query', 'limit', 'mode'}:
                raise ValueError('only query, limit and mode are accepted')
            query = args.get('query')
            limit, mode = args.get('limit', 10), args.get('mode', 'latest')
            if not isinstance(query, str) or not query.strip() or len(query) > 1000:
                raise ValueError('query must contain 1-1000 characters')
            if type(limit) is not int or not 1 <= limit <= 30 or mode not in {'latest', 'top'}:
                raise ValueError('limit must be 1-30 and mode latest/top')
        except (ValueError, TypeError):
            return web.json_response({'error': 'invalid_search_arguments'}, status=400)
        if lock.locked():
            return web.json_response({'error': 'search_busy'}, status=409)
        async with lock:
            try:
                result = await asyncio.wait_for(adapter.search(query.strip(), limit, mode), timeout=55)
                return web.json_response(result)
            except AuthRequired:
                revoke(); start_login(proxy_mode=proxy_mode)
                return web.json_response({'error': 'auth_required', 'records': [],
                    'message': '请在本机 X 登录窗口完成登录后重试。'}, status=401)
            except Exception:
                # 浏览器异常可能携带请求信息；不透传给生成代码或模型。
                return web.json_response({'error': 'search_unavailable', 'records': []}, status=502)
    app = web.Application(client_max_size=8192)
    app.router.add_post('/search', search)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    try:
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = runner.addresses[0][1]
        yield {'SEARCHOS_BROWSER_URL': f'http://127.0.0.1:{port}/search', 'SEARCHOS_BROWSER_TOKEN': token}
    finally:
        await runner.cleanup()


@asynccontextmanager
async def browser_bridge(profile: str, *, proxy_mode: str = 'inherit'):
    state = require_state(profile, proxy_mode=proxy_mode)
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(**browser_options(headless=True, proxy_mode=proxy_mode))
        try:
            context = await browser.new_context(storage_state=state, service_workers='block')
            async def route(request_route):
                hostname = (urlsplit(request_route.request.url).hostname or '').lower()
                if any(hostname == domain or hostname.endswith('.'+domain) for domain in ('x.com', 'twitter.com', 'twimg.com')):
                    await request_route.continue_()
                else:
                    await request_route.abort()
            await context.route('**/*', route)
            async with serve_search(XSearchBrowser(context), proxy_mode=proxy_mode) as env:
                yield env
        finally:
            await browser.close()
