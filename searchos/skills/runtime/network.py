"""单次执行的网络路由配置；不修改宿主环境或系统代理。"""
from __future__ import annotations

import os
import json
from pathlib import Path
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


def command_network_mode(package: Path, argv: list[str]) -> str:
    """从包配置和业务参数选择认证浏览器线路；宿主只读取数据。"""
    from searchos.skills.runtime.network import validate_proxy_mode
    from searchos.skills.runtime.paths import resolve_resource_file

    path = package / 'scripts/network.json'
    if not path.exists() and not path.is_symlink():
        return 'inherit'
    path = resolve_resource_file(package, 'scripts/network.json')
    if path.stat().st_size > 64_000:
        raise ValueError('package browser network configuration exceeds limit')
    config = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(config, dict) or config.get('version') != 1:
        raise ValueError('invalid package browser network configuration')
    functions, aliases = config.get('functions', {}), config.get('aliases', {})
    if not isinstance(functions, dict) or not isinstance(aliases, dict):
        raise ValueError('invalid package browser network function mapping')
    known = set(functions) | set(aliases)
    args = argv[2:]
    params, options = {}, {}
    file_parameters = False
    index = 0
    while index < len(args):
        argument = args[index]
        index += 1
        if argument == '--':
            break
        option, equal, value = argument.partition('=')
        if option not in {'--params', '--input', '--params-file', '--function', '--method'}:
            continue
        if not equal:
            if index == len(args):
                raise ValueError('browser business selector requires a value')
            value = args[index]
            index += 1
        if option == '--params-file':
            file_parameters = True
        if option in {'--params', '--input'}:
            if option == '--params' or value.lstrip().startswith(('{', '[')):
                decoded = json.loads(value)
                if not isinstance(decoded, dict):
                    raise ValueError('browser business parameters must be a JSON object')
                if any(key in params and key in decoded and params[key] != decoded[key]
                       for key in ('function', 'method')):
                    raise ValueError('conflicting browser business function selectors')
                params.update(decoded)
            else:
                file_parameters = True
        elif option in {'--function', '--method'}:
            options[option[2:]] = value
    # 文件输入留在原沙箱内读取；多线路配置要求 argv 明确指定业务函数。
    if file_parameters and not options.get('function'):
        configured = [config.get('default', 'inherit'), *functions.values()]
        modes = {validate_proxy_mode(value.get('mode', 'inherit') if isinstance(value, dict)
                                     else value) for value in configured}
        if len(modes) > 1:
            raise ValueError('browser network selection requires an inline business function '
                             'when file parameters can select different routes')
    params.update(options)
    selected = params.get('function') or params.get('method')
    if not selected and args and args[0] in known:
        selected = args[0]
    selected = selected or Path(argv[1]).stem
    if not isinstance(selected, str):
        raise ValueError('browser business function must be a string')
    selected = aliases.get(selected, selected)
    if not isinstance(selected, str):
        raise ValueError('invalid package browser network function alias')
    mode = functions.get(selected, config.get('default', 'inherit'))
    if isinstance(mode, dict):
        mode = mode.get('mode', 'inherit')
    return validate_proxy_mode(mode)
