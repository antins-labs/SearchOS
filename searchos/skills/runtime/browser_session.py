"""按站点独占的持久浏览器；工作进程与命令分别使用 OS 文件隔离。"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit

current_session = ContextVar('skill_browser_session', default=None)
AUTH_FIELD = re.compile(r'^(authorization|cookies?|set-cookie|password|passwd|api[_-]?key|access_token|refresh_token|id_token|auth_token|secret|storage_state|browser_cdp_url)$', re.I)


def normalize_site(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('browser host must be a hostname')
    host = value.lower().rstrip('.').encode('idna').decode('ascii')
    if len(host) > 253 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host) or '..' in host:
        raise ValueError('browser host must be a hostname')
    return host


def storage_root() -> Path:
    from searchos.config.settings import settings
    root = Path(settings.browser_auth_dir).expanduser()
    for ancestor in (root, *root.parents):
        if ancestor.is_symlink() and ancestor not in (Path('/tmp'), Path('/var')):
            raise ValueError('browser storage must not contain symbolic links')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    return root.resolve()


def _folder(name):
    path = storage_root() / name
    if path.is_symlink():
        raise ValueError('browser storage must not be a symbolic link')
    path.mkdir(exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _lock(site):
    path = _folder('locks') / (normalize_site(site) + '.lock')
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise ValueError('browser_profile_busy: 该站点会话正由其他任务使用') from None
    return fd


def list_sessions():
    results = []
    paths = {path.name: path for path in _folder('profiles').iterdir()
             if path.is_dir() and not path.is_symlink()}
    paths.update({path.stem: path for path in _folder('vaults').glob('*.enc') if not path.is_symlink()})
    for site, path in sorted(paths.items()):
        try:
            fd = _lock(site)
        except ValueError:
            busy = True
        else:
            busy = False
            os.close(fd)
        results.append({'site': site, 'busy': busy, 'updated_at': path.stat().st_mtime})
    return results


def clear_session(site):
    site = normalize_site(site)
    fd = _lock(site)
    try:
        path = _folder('profiles') / site
        if path.is_symlink():
            raise ValueError('browser profile must not be a symbolic link')
        if path.exists():
            shutil.rmtree(path)
        vault = _folder('vaults') / (site + '.enc')
        if vault.is_symlink():
            raise ValueError('browser vault must not be a symbolic link')
        vault.unlink(missing_ok=True)
        key = _folder('keys') / (site + '.key')
        if key.is_symlink():
            raise ValueError('browser key must not be a symbolic link')
        key.unlink(missing_ok=True)
        recovery = _folder('recovery')
        for path in recovery.iterdir():
            if re.fullmatch(re.escape(site) + r'-[0-9a-f]{12}', path.name) and path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
    finally:
        os.close(fd)


def validate_metadata(metadata):
    profile = metadata.get('searchos-browser-profile')
    entries = metadata.get('searchos-browser-entries', '')
    if profile is None and not entries:
        return None, []
    if profile != 'managed':
        raise ValueError('unsupported browser profile; use searchos-browser-profile: managed')
    host = normalize_site(metadata.get('host'))
    if not isinstance(entries, str) or not entries.strip():
        raise ValueError('managed browser requires searchos-browser-entries')
    paths = [entry.strip() for entry in entries.split(',')]
    if any(not entry or Path(entry).is_absolute() or '..' in Path(entry).parts for entry in paths):
        raise ValueError('browser entries must be relative package paths')
    return host, paths


def command_profile(package, argv):
    path = Path(package) / 'SKILL.md'
    if not path.is_file():
        return None
    import yaml
    parts = path.read_text().split('---', 2)
    if len(parts) != 3:
        return None
    host, entries = validate_metadata((yaml.safe_load(parts[1]) or {}).get('metadata', {}))
    return host if len(argv) > 1 and argv[1] in entries and not {'--help', '-h'}.intersection(argv) else None


def user_action(result):
    """只接受完整 JSON 顶层的显式站点信号。"""
    try:
        value = json.loads(result.get('stdout', ''))
        if (not isinstance(value, dict) or value.get('status') != 'user_action_required'
                or value.get('kind') not in {'login', 'verification'}
                or not isinstance(value.get('message'), str) or not value['message'].strip()):
            return None
        url = urlsplit(value.get('url', ''))
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
            return None
        # 展示地址保留页面位置；验证查询参数留在当前浏览器页面。
        return {'kind': value['kind'], 'message': value['message'][:2000],
                'url': urlunsplit((url.scheme, url.netloc, url.path, '', ''))}
    except (ValueError, TypeError):
        return None


def clean_private(value, secrets=()):
    if isinstance(value, dict):
        return {key: '[REDACTED]' if AUTH_FIELD.fullmatch(str(key)) else clean_private(item, secrets)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_private(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in sorted(set(secrets), key=len, reverse=True):
            if secret and len(secret) >= 4:
                value = value.replace(secret, '[REDACTED]')
        value = re.sub(r'(?i)(Bearer\s+)[\w.\-]+', r'\1[REDACTED]', value)
        value = re.sub(r'wss?://127\.0\.0\.1:\d+/[A-Za-z0-9_-]{40,}', '[REDACTED]', value)
        # JSON 字符串、请求头和常见赋值中的认证字段。
        value = re.sub(r'(?i)([\"\x27]?(?:authorization|cookie|set-cookie|password|access_token|refresh_token|auth_token)[\"\x27]?\s*[:=]\s*)([\"\x27])[^\"\x27]*\2',
                       r'\1\2[REDACTED]\2', value)
        return value
    return value


class BrowserSession:
    def __init__(self, site, *, allow_interaction=False, on_action=None, checkpoint=None):
        self.site = normalize_site(site)
        self.allow_interaction, self.on_action = allow_interaction, on_action
        self.checkpoint = checkpoint or (lambda: None)
        self.process = self.temporary = self.lock_fd = None
        self.vault = self.network_proxy = self.profile = None
        self.endpoint = self.proxy_mode = None
        self.action_url = None
        self.secrets = set()
        self.blocked = {}
        self.blocked_requests = {}
        self.rpc_lock = asyncio.Lock()

    async def _rpc(self, action):
        async with self.rpc_lock:
            self.process.stdin.write((json.dumps(action) + '\n').encode())
            await self.process.stdin.drain()
            line = await asyncio.wait_for(self.process.stdout.readline(), 20)
            if not line:
                if self.process.stderr is not None:
                    self.diagnostic = self.clean((await self.process.stderr.read(8000)).decode(errors='replace'))
                raise ValueError('browser_unavailable: 浏览器工作进程已退出')
            result = json.loads(line)
            if result.get('error'):
                if not getattr(self, 'diagnostic', None):
                    self.diagnostic = self.clean(result.get('detail', result['error']))
                raise ValueError('browser_unavailable: ' + result['error'])
            return result

    async def ensure(self, proxy_mode='inherit'):
        if self.process is not None:
            if self.proxy_mode != proxy_mode:
                raise ValueError('browser_network_changed: 当前会话须沿用已选浏览器线路')
            if self.process.returncode is not None:
                raise ValueError('browser_unavailable: 浏览器工作进程已退出')
            return {'BROWSER_CDP_URL': self.endpoint}
        from searchos.skills.runtime.command_runtime import _backend, _environment
        from searchos.skills.runtime.network import browser_proxy_options
        from searchos.skills.runtime.browser_vault import ProfileVault
        from searchos.skills.runtime.browser_gateway import BrowserPolicy, NetworkProxy
        from searchos.config.settings import settings
        options = browser_proxy_options(proxy_mode)
        engine_roots = ()
        chrome = Path('/Applications/Google Chrome.app')
        if sys.platform == 'darwin' and chrome.is_dir():
            engine_roots = (chrome.resolve(),)
        self.lock_fd = _lock(self.site)
        try:
            legacy = _folder('profiles') / self.site
            if legacy.is_symlink():
                raise ValueError('browser profile must not be a symbolic link')
            self.vault = await asyncio.to_thread(ProfileVault, storage_root(), self.site)
            self.temporary = tempfile.TemporaryDirectory(prefix='searchos-browser-')
            work = Path(self.temporary.name).resolve()
            profile = work / 'profile'
            if legacy.is_dir() and not self.vault.path.exists():
                await asyncio.to_thread(self.vault.save, legacy)
            await asyncio.to_thread(self.vault.restore, profile)
            self.profile = profile
            self.secrets.add(str(profile))
            if legacy.is_dir():
                await asyncio.to_thread(shutil.rmtree, legacy)
            domains = settings.browser_allowed_domains.get(self.site, [self.site.removeprefix('www.')])
            if not domains:
                raise ValueError('browser network domain allowlist is empty')
            domains = [normalize_site(value) for value in domains]
            self.network_proxy = NetworkProxy(BrowserPolicy(domains), options.get('proxy', {}).get('server'))
            await self.network_proxy.start()
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            gateway_port = listener.getsockname()[1]
            script = Path(__file__).resolve()
            command, _ = _backend([sys.executable, '-I', str(script), '--worker'], script, work, True,
                                  (*engine_roots, script.with_name('browser_gateway.py')), browser_profile=profile,
                                  network_ports=(self.network_proxy.port, gateway_port), listen_loopback=True,
                                  desktop=self.allow_interaction or bool(engine_roots))
            env = _environment(work, network=True, proxy_mode=proxy_mode)
            if sys.platform == 'darwin':
                env['MAC_CHROMIUM_TMPDIR'] = str(work)
            if self.allow_interaction:
                for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_RUNTIME_DIR'):
                    if key in os.environ:
                        env[key] = os.environ[key]
            try:
                self.process = await asyncio.create_subprocess_exec(*command, cwd=work, env=env,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, start_new_session=True, pass_fds=(listener.fileno(),))
                response = await self._rpc({'action': 'start', 'profile': str(profile),
                    'headless': not self.allow_interaction, 'domains': domains,
                    'proxy_port': self.network_proxy.port, 'listener_fd': listener.fileno(),
                    'executable': str(chrome / 'Contents/MacOS/Google Chrome') if engine_roots else None})
            finally:
                listener.close()
            self.endpoint, self.proxy_mode = response['endpoint'], proxy_mode
            self.secrets.update((self.endpoint, str(profile)))
            await self.refresh_secrets()
            return {'BROWSER_CDP_URL': self.endpoint}
        except BaseException:
            await self.close()
            raise

    async def show(self):
        if not self.allow_interaction or self.process is None:
            raise ValueError('该任务没有可交互浏览器')
        await self._rpc({'action': 'show', 'url': self.action_url})

    async def refresh_secrets(self):
        if self.process and self.process.returncode is None:
            response = await self._rpc({'action': 'secrets'})
            self.secrets.update(response.get('values', []))

    def clean(self, value):
        return clean_private(value, self.secrets)

    async def resolve(self, result, request, *, after_confirmation=False):
        action = user_action(result)
        if action is None:
            return False, result
        self.action_url = action['url']
        key = json.dumps(action, sort_keys=True)
        blocked = {**result, 'status': 'blocked', 'external_blocked': True,
                  'next_action': 'wait_external', 'user_action': action,
                  'error': action['message']}
        self.checkpoint()
        if after_confirmation:
            return False, {**blocked, 'user_action_completed': True,
                'error': '用户确认后重试仍要求操作。请检查当前页面和脚本逻辑，再决定是否需要新的用户操作。'}
        if key not in self.blocked and self.allow_interaction and self.on_action:
            decision = await self.on_action(action, self, self.clean(request))
            if decision == 'continue':
                if request.get('code') is not None:
                    return False, {**result, 'status': 'user_action_completed', 'user_action_completed': True,
                        'user_action': action, 'next_action': 'recheck_browser',
                        'message': '用户已确认完成操作。请重新检查当前浏览器页面并继续实际取数。'}
                return True, blocked
        self.blocked[key] = action
        self.blocked_requests[self.request_key(request)] = blocked
        return False, blocked

    @staticmethod
    def request_key(request):
        return json.dumps({key: value for key, value in request.items() if key != 'role'}, sort_keys=True)

    async def close(self):
        from searchos.skills.runtime.command_runtime import _kill
        persisted = False
        try:
            if self.process:
                try:
                    await asyncio.wait_for(self._rpc({'action': 'close'}), 20)
                except (Exception, asyncio.CancelledError):
                    pass
                await _kill(self.process)
            if self.profile is not None and self.vault is not None:
                await asyncio.to_thread(self.vault.save, self.profile)
            persisted = True
        finally:
            self.process = None
            self.endpoint = None
            if self.network_proxy is not None:
                await self.network_proxy.close()
                self.network_proxy = None
            if self.temporary:
                if not persisted and self.profile is not None:
                    recovery = _folder('recovery') / (self.site + '-' + os.urandom(6).hex())
                    shutil.move(str(self.profile), recovery)
                self.temporary.cleanup()
                self.temporary = None
            self.profile = self.vault = None
            if self.lock_fd is not None:
                os.close(self.lock_fd)
                self.lock_fd = None


async def _worker():
    """隔离进程入口；stdin EOF 随宿主退出关闭 profile。"""
    from playwright.async_api import async_playwright
    import importlib.util
    spec = importlib.util.spec_from_file_location('browser_gateway', Path(__file__).with_name('browser_gateway.py'))
    gateway_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gateway_module)
    BrowserGateway, BrowserPolicy = gateway_module.BrowserGateway, gateway_module.BrowserPolicy
    os.umask(0o077)
    context = gateway = browser = None
    async with async_playwright() as playwright:
        try:
            while line := await asyncio.to_thread(sys.stdin.readline):
                request = json.loads(line)
                try:
                    action = request['action']
                    result = {}
                    if action == 'start':
                        profile = Path(request['profile'])
                        gateway = BrowserGateway(BrowserPolicy(request['domains']))
                        result['endpoint'] = await gateway.start(request['executable'] or playwright.chromium.executable_path,
                            profile, headless=request['headless'], proxy_port=request['proxy_port'],
                            listener_fd=request['listener_fd'])
                        browser = await playwright.chromium.connect_over_cdp(gateway.owner_endpoint)
                        context = browser.contexts[0]
                    elif action == 'show':
                        matches = [page for page in context.pages
                            if urlunsplit((*urlsplit(page.url)[:3], '', '')) == request.get('url')]
                        page = matches[-1] if matches else context.pages[-1] if context.pages else await context.new_page()
                        cdp = await context.new_cdp_session(page)
                        window = await cdp.send('Browser.getWindowForTarget')
                        await cdp.send('Browser.setWindowBounds', {'windowId': window['windowId'],
                            'bounds': {'windowState': 'normal'}})
                        await page.bring_to_front()
                        await cdp.detach()
                    elif action == 'secrets':
                        state = await context.storage_state()
                        values = [item['value'] for item in state['cookies']
                                  if item['name'].lower() != 'xsectoken']
                        values.extend(item['value'] for origin in state['origins']
                            for item in origin['localStorage'] if AUTH_FIELD.fullmatch(item['name']))
                        result['values'] = [value for value in values if len(value) >= 4]
                    elif action == 'close':
                        if browser:
                            await browser.close()
                        if gateway:
                            await gateway.close()
                        gateway = browser = None
                        context = None
                    else:
                        raise ValueError('unsupported browser operation')
                except Exception as exc:
                    result = {'error': type(exc).__name__, 'detail': str(exc)}
                print(json.dumps(result), flush=True)
                if request['action'] == 'close':
                    break
        finally:
            if gateway:
                await gateway.close()


if __name__ == '__main__' and sys.argv[1:] == ['--worker']:
    asyncio.run(_worker())
