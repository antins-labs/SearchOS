"""包内网络配置；仅依赖标准库与技能声明的客户端。"""
from __future__ import annotations

import contextvars
import functools
import inspect
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit, urlunsplit

_CAPABILITY = contextvars.ContextVar('skill_network_capability', default='package')
_CONFIG_PATH = Path(__file__).with_name('network.json')


def _config():
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'version': 1, 'default': 'inherit', 'functions': {}}


def mode():
    """选择包内函数线路，诊断调用可临时覆盖。"""
    diagnostic = os.environ.get('SEARCHOS_NETWORK_DIAGNOSTIC_MODE')
    if diagnostic in ('direct', 'proxy', 'inherit'):
        return diagnostic
    config = _config()
    capability = config.get('aliases', {}).get(_CAPABILITY.get(), _CAPABILITY.get())
    selected = config.get('functions', {}).get(capability, config.get('default', 'inherit'))
    if isinstance(selected, dict):
        selected = selected.get('mode', 'inherit')
    if selected not in ('direct', 'proxy', 'inherit'):
        raise ValueError('invalid package network mode')
    return selected


def entrypoint(function=None, *, capability_id=None, cli=False):
    """在普通函数调用范围内选择业务能力。"""
    def decorate(fn):
        def selected(args, kwargs):
            params = args[0] if args and isinstance(args[0], dict) else kwargs.get('params')
            if isinstance(params, dict):
                return str(params.get('function') or params.get('method') or capability_id or 'package')
            if cli:
                argv = args[0] if args and isinstance(args[0], (list, tuple)) else sys.argv[1:]
                config = _config()
                known = set(config.get('functions', {})) | set(config.get('aliases', {}))
                if argv and isinstance(argv[0], str) and argv[0] in known:
                    return argv[0]
            return capability_id or 'package'
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_call(*args, **kwargs):
                token = _CAPABILITY.set(selected(args, kwargs))
                try:
                    return await fn(*args, **kwargs)
                finally:
                    _CAPABILITY.reset(token)
            return async_call
        @functools.wraps(fn)
        def sync_call(*args, **kwargs):
            token = _CAPABILITY.set(selected(args, kwargs))
            try:
                return fn(*args, **kwargs)
            finally:
                _CAPABILITY.reset(token)
        return sync_call
    return decorate(function) if function is not None else decorate


def _proxy():
    for name in ('https_proxy', 'HTTPS_PROXY', 'http_proxy', 'HTTP_PROXY', 'all_proxy', 'ALL_PROXY'):
        if os.environ.get(name):
            return os.environ[name]
    raise RuntimeError('package network mode requires a standard proxy environment variable')


def _safe_url(value):
    try:
        parsed = urlsplit(str(value))
        host = parsed.hostname or ''
        if ':' in host:
            host = '[' + host + ']'
        if parsed.port:
            host += ':' + str(parsed.port)
        path = re.sub(r'(?<=/)[A-Za-z0-9_-]{32,}(?=/|$)', '[redacted]', parsed.path)
        return urlunsplit((parsed.scheme, host, path, '', ''))
    except (ValueError, TypeError):
        return '[invalid URL]'


def _audit(client, url, status=None, error=None):
    if os.environ.get('SEARCHOS_NETWORK_AUDIT') != '1':
        return
    item = {'client': client, 'function': _CAPABILITY.get(), 'mode': mode(), 'url': _safe_url(url)}
    if status is not None:
        item['status'] = int(status)
    if error is not None:
        item['error'] = type(error).__name__
    try:
        with Path('network.log').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(item, ensure_ascii=False) + '\n')
    except OSError:
        pass


def aiohttp_session(*args, **kwargs):
    import aiohttp
    selected = mode()
    if selected in ('direct', 'proxy'):
        kwargs['trust_env'] = False
        kwargs['proxy'] = _proxy() if selected == 'proxy' else None
        kwargs.pop('proxy_auth', None)
    if os.environ.get('SEARCHOS_NETWORK_AUDIT') == '1':
        trace = aiohttp.TraceConfig()
        async def finished(session, context, params):
            _audit('aiohttp', params.url, params.response.status)
        async def failed(session, context, params):
            _audit('aiohttp', params.url, error=params.exception)
        trace.on_request_end.append(finished)
        trace.on_request_exception.append(failed)
        kwargs['trace_configs'] = [*kwargs.get('trace_configs', []), trace]
    return aiohttp.ClientSession(*args, **kwargs)


def _httpx_options(kwargs, asynchronous):
    selected = mode()
    if selected in ('direct', 'proxy'):
        kwargs['trust_env'] = False
        kwargs['proxy'] = _proxy() if selected == 'proxy' else None
    if os.environ.get('SEARCHOS_NETWORK_AUDIT') == '1':
        hooks = {key: list(value) for key, value in kwargs.get('event_hooks', {}).items()}
        if asynchronous:
            async def response_hook(response):
                _audit('httpx', response.request.url, response.status_code)
        else:
            def response_hook(response):
                _audit('httpx', response.request.url, response.status_code)
        hooks.setdefault('response', []).append(response_hook)
        kwargs['event_hooks'] = hooks
    return kwargs


def httpx_client(*args, **kwargs):
    import httpx
    return httpx.Client(*args, **_httpx_options(kwargs, False))


def httpx_async_client(*args, **kwargs):
    import httpx
    return httpx.AsyncClient(*args, **_httpx_options(kwargs, True))


def urllib_build_opener(*handlers):
    import urllib.request
    selected = mode()
    if selected in ('direct', 'proxy'):
        handlers = tuple(handler for handler in handlers
                         if not isinstance(handler, urllib.request.ProxyHandler)
                         and handler is not urllib.request.ProxyHandler)
        mapping = {} if selected == 'direct' else {'http': _proxy(), 'https': _proxy()}
        handlers = (*handlers, urllib.request.ProxyHandler(mapping))
    if os.environ.get('SEARCHOS_NETWORK_AUDIT') == '1':
        class AuditHandler(urllib.request.BaseHandler):
            def http_response(self, request, response):
                _audit('urllib', response.geturl(), response.status)
                return response
            https_response = http_response
        handlers = (*handlers, AuditHandler())
    return urllib.request.build_opener(*handlers)


def urllib_urlopen(*args, **kwargs):
    import urllib.request
    if mode() == 'inherit' and os.environ.get('SEARCHOS_NETWORK_AUDIT') != '1':
        return urllib.request.urlopen(*args, **kwargs)
    context = kwargs.pop('context', None)
    handlers = [urllib.request.HTTPSHandler(context=context)] if context is not None else []
    try:
        return urllib_build_opener(*handlers).open(*args, **kwargs)
    except Exception as exc:
        url = args[0] if args else kwargs.get('url', '')
        _audit('urllib', getattr(url, 'full_url', url), error=exc)
        raise


def _browser_options(kwargs, browser_type):
    selected = mode()
    if selected == 'direct':
        kwargs.pop('proxy', None)
        if getattr(browser_type, 'name', 'chromium') == 'chromium':
            kwargs['args'] = [*kwargs.get('args', []), '--no-proxy-server']
    elif selected == 'proxy':
        value = urlsplit(_proxy())
        server = urlunsplit((value.scheme, value.hostname + (':' + str(value.port) if value.port else ''), '', '', ''))
        proxy = {'server': server}
        if value.username is not None:
            proxy['username'] = unquote(value.username)
        if value.password is not None:
            proxy['password'] = unquote(value.password)
        bypass = os.environ.get('no_proxy') or os.environ.get('NO_PROXY')
        if bypass:
            proxy['bypass'] = bypass
        kwargs['proxy'] = proxy
    return kwargs


def _browser_audit(target):
    if os.environ.get('SEARCHOS_NETWORK_AUDIT') == '1':
        target.on('response', lambda response: _audit('playwright', response.url, response.status))
        target.on('requestfailed', lambda request: _audit('playwright', request.url, error=ConnectionError()))
    return target


def _result(value, transform):
    if inspect.isawaitable(value):
        async def resolved():
            return transform(await value)
        return resolved()
    return transform(value)


def browser_launch(browser_type, *args, **kwargs):
    return browser_type.launch(*args, **_browser_options(kwargs, browser_type))


def browser_launch_persistent_context(browser_type, *args, **kwargs):
    return _result(browser_type.launch_persistent_context(*args, **_browser_options(kwargs, browser_type)), _browser_audit)


def browser_new_context(browser, *args, **kwargs):
    return _result(browser.new_context(*args, **kwargs), _browser_audit)


def browser_new_page(browser_or_context, *args, **kwargs):
    return _result(browser_or_context.new_page(*args, **kwargs), _browser_audit)


def requests_call(function, *args, **kwargs):
    selected = mode()
    if selected in ('direct', 'proxy'):
        mapping = {'http': '', 'https': ''} if selected == 'direct' else {'http': _proxy(), 'https': _proxy()}
        kwargs['proxies'] = mapping
    try:
        response = function(*args, **kwargs)
        _audit('requests', getattr(response, 'url', args[0] if args else ''), getattr(response, 'status_code', None))
        return response
    except Exception as exc:
        _audit('requests', args[0] if args else '', error=exc)
        raise


def requests_session(function, *args, **kwargs):
    session = function(*args, **kwargs)
    selected = mode()
    if selected in ('direct', 'proxy'):
        session.trust_env = False
        session.proxies.update({} if selected == 'direct' else {'http': _proxy(), 'https': _proxy()})
    return session
