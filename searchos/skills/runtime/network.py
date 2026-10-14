"""单次执行的网络路由配置；不修改宿主环境或系统代理。"""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

PROXY_MODES = ('inherit', 'direct', 'proxy')
PROXY_SCHEMA = {
    'type': 'string', 'enum': list(PROXY_MODES), 'default': 'inherit',
    'description': 'inherit: configured environment; direct: bypass application proxies; proxy: require configured proxy. Does not change OS VPN/TUN routing.',
}


def validate_proxy_mode(mode: str) -> str:
    if mode not in PROXY_MODES:
        raise ValueError('proxy_mode must be inherit, direct or proxy')
    return mode


def sanitize_proxy(value: str) -> str:
    try:
        parsed = urlsplit(value if '://' in value else 'http://' + value)
        if parsed.scheme not in {'http', 'https', 'socks5', 'socks5h'} or not parsed.hostname:
            return ''
        host = parsed.hostname
        if ':' in host:
            host = f'[{host}]'
        return urlunsplit((parsed.scheme, f'{host}:{parsed.port}' if parsed.port else host, '', '', ''))
    except (TypeError, ValueError):
        return ''


def proxy_environment(mode: str = 'inherit', *, environ=None) -> dict[str, str]:
    """返回白名单环境；去除认证信息，并避免 macOS urllib 回退到系统代理。"""
    validate_proxy_mode(mode)
    source = os.environ if environ is None else environ
    env = {'SEARCHOS_PROXY_MODE': mode}
    if mode == 'direct':
        return {**env, 'NO_PROXY': '*', 'no_proxy': '*'}
    for key in ('http_proxy', 'https_proxy', 'all_proxy'):
        # WebUI 配置导出大写变量；统一大小写，避免旧 shell 变量覆盖当前配置。
        if value := sanitize_proxy(source.get(key.upper()) or source.get(key) or ''):
            env[key] = env[key.upper()] = value
    if mode == 'proxy' and not any(key in env for key in ('http_proxy', 'https_proxy', 'all_proxy')):
        raise ValueError('proxy_unavailable: no configured proxy; choose direct or configure a proxy')
    bypass = source.get('NO_PROXY') or source.get('no_proxy') or ''
    if mode == 'proxy':
        # Explicit proxy comparisons must not silently inherit site bypass rules.
        proxy = env.get('https_proxy') or env.get('http_proxy') or env['all_proxy']
        for key in ('http_proxy', 'https_proxy', 'all_proxy'):
            env[key] = env[key.upper()] = proxy
        bypass = 'localhost,127.0.0.1,::1'
    if bypass:
        env['NO_PROXY'] = env['no_proxy'] = bypass
    return env


def browser_proxy_options(mode: str = 'inherit', *, environ=None) -> dict:
    """Chromium 显式启动参数；环境变量本身不控制 Playwright 的代理。"""
    env = proxy_environment(mode, environ=environ)
    if mode == 'direct':
        return {'args': ['--no-proxy-server']}
    proxy = env.get('https_proxy') or env.get('http_proxy') or env.get('all_proxy')
    if not proxy:
        return {}
    return {'proxy': {'server': proxy, 'bypass': env.get('no_proxy', '')}}
