"""浏览器私有管道、会话鉴权与站点网络边界。"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import sys
from urllib.parse import urlsplit


class BrowserPolicy:
    def __init__(self, domains):
        self.domains = tuple(str(d).lower().rstrip('.') for d in domains)

    def allows_host(self, host):
        host = host.lower().rstrip('.')
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return any(host == d or host.endswith('.' + d) for d in self.domains)

    def allows_url(self, url):
        if url == 'about:blank':
            return True
        try:
            value = urlsplit(url)
            return (value.scheme in {'http', 'https'} and not value.username and not value.password
                    and value.port in (None, 80, 443) and self.allows_host(value.hostname or ''))
        except ValueError:
            return False

    def allows_command(self, message):
        method, params = message.get('method', ''), message.get('params', {})
        if method in {'Storage.getCookies', 'Storage.setCookies', 'Storage.clearCookies',
                      'Network.getCookies', 'Network.getAllCookies', 'Network.setCookies', 'Network.setCookie',
                      'Network.clearBrowserCookies', 'Target.sendMessageToTarget', 'Target.exposeDevToolsProtocol',
                      'Target.attachToBrowserTarget', 'Browser.close', 'Browser.crash',
                      'Browser.getBrowserCommandLine', 'Browser.executeBrowserCommand'}:
            return False
        if method.split('.')[0] not in {'Browser', 'Target', 'Page', 'Runtime', 'DOM', 'DOMSnapshot',
                'CSS', 'Accessibility', 'Input', 'Network', 'Log', 'Emulation', 'Performance', 'Security', 'Fetch'}:
            return False
        if method.startswith('Browser.') and method not in {'Browser.getVersion', 'Browser.getBrowserContexts',
                'Browser.setDownloadBehavior', 'Browser.getWindowForTarget', 'Browser.getWindowBounds', 'Browser.setWindowBounds'}:
            return False
        if method == 'Browser.setDownloadBehavior' and params.get('behavior') != 'deny':
            return False
        return 'url' not in params or self.allows_url(params['url'])


def redact_headers(value):
    if isinstance(value, list):
        return [redact_headers(v) for v in value]
    if isinstance(value, dict):
        return {k: ([] if k.lower() in {'associatedcookies', 'blockedcookies'} else
                   '[REDACTED]' if k.lower() in {'cookie', 'set-cookie', 'authorization', 'proxyauthorization',
                    'proxy-authorization', 'headerstext', 'associatedcookies', 'blockedcookies'}
                    else redact_headers(v)) for k, v in value.items()}
    return value


class NetworkProxy:
    """先检查域名和解析地址，再连接固定的公网 IP。"""
    def __init__(self, policy, upstream=None):
        self.policy, self.server = policy, None
        self.upstream = urlsplit(upstream) if upstream else None
        if self.upstream and self.upstream.scheme not in {'http', 'https', 'socks5', 'socks5h'}:
            raise ValueError('unsupported browser upstream proxy')
        self.connections = set()

    async def start(self):
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', 0, limit=16384)
        self.port = self.server.sockets[0].getsockname()[1]

    async def addresses(self, host, port):
        records = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        if not records or any(not ipaddress.ip_address(r[4][0]).is_global for r in records):
            raise ValueError('private network address denied')
        return records

    async def open_remote(self, address, port, family):
        if self.upstream is None:
            return await asyncio.open_connection(address, port, family=family)
        proxy = self.upstream
        reader, writer = await asyncio.open_connection(proxy.hostname,
            proxy.port or (1080 if proxy.scheme.startswith('socks') else 8080),
            ssl=proxy.scheme == 'https')
        try:
            if proxy.scheme.startswith('socks'):
                writer.write(b'\x05\x01\x00')
                await writer.drain()
                if await reader.readexactly(2) != b'\x05\x00':
                    raise OSError('upstream proxy authentication failed')
                ip = ipaddress.ip_address(address)
                writer.write(b'\x05\x01\x00' + (b'\x01' if ip.version == 4 else b'\x04') + ip.packed + port.to_bytes(2, 'big'))
                await writer.drain()
                reply = await reader.readexactly(4)
                if reply[:2] != b'\x05\x00' or reply[3] not in (1, 4):
                    raise OSError('upstream proxy connection failed')
                await reader.readexactly(6 if reply[3] == 1 else 18)
            else:
                host = f'[{address}]' if ':' in address else address
                writer.write(f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n'.encode())
                await writer.drain()
                header = await reader.readuntil(b'\r\n\r\n')
                if header.split(b' ', 2)[1] != b'200':
                    raise OSError('upstream proxy connection failed')
            return reader, writer
        except BaseException:
            writer.close()
            raise

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.connections.add(task)
        remote = None
        try:
            header = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 10)
            method, target, _ = header.split(b'\r\n', 1)[0].decode('ascii').split(' ', 2)
            value = urlsplit('https://' + target if method == 'CONNECT' else target)
            port = value.port or (443 if method == 'CONNECT' else 80)
            if (not self.policy.allows_host(value.hostname or '') or value.username or value.password
                    or port != (443 if method == 'CONNECT' else 80)
                    or (method != 'CONNECT' and value.scheme != 'http')):
                raise ValueError('network destination denied')
            addresses = await self.addresses(value.hostname, port)
            error = None
            for family, _, _, _, address in addresses:
                try:
                    incoming, remote = await asyncio.wait_for(self.open_remote(address[0], port, family), 10)
                    break
                except OSError as exc:
                    error = exc
            if remote is None:
                raise error or OSError('network connection failed')
            if method == 'CONNECT':
                writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                await writer.drain()
            else:
                lines = header.split(b'\r\n')
                path = value.path or '/'
                if value.query:
                    path += '?' + value.query
                lines[0] = f'{method} {path} HTTP/1.1'.encode()
                lines = [line for line in lines if not line.lower().startswith((b'proxy-authorization:', b'proxy-connection:'))]
                remote.write(b'\r\n'.join(lines))
                await remote.drain()

            async def copy(source, sink):
                while chunk := await source.read(65536):
                    sink.write(chunk)
                    await sink.drain()
            pumps = [asyncio.create_task(copy(reader, remote)), asyncio.create_task(copy(incoming, writer))]
            try:
                await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for pump in pumps:
                    pump.cancel()
                await asyncio.gather(*pumps, return_exceptions=True)
        except (ValueError, OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            if remote is None:
                writer.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
        finally:
            if remote:
                remote.close()
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            finally:
                self.connections.discard(task)

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        tasks = list(self.connections)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class BrowserGateway:
    """每个客户端独占一个 browser CDP session；原始 Chrome 只开放管道。"""
    def __init__(self, policy):
        self.policy = policy
        self.client_token, self.owner_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.pending, self.clients = {}, {}
        self.sequence = 0
        self.process = self.reader_task = self.runner = None
        self.stderr_task = None
        self.stderr_tail = b''

    async def capture_stderr(self):
        while chunk := await self.process.stderr.read(4096):
            self.stderr_tail = (self.stderr_tail + chunk)[-8000:]

    async def start(self, executable, profile, *, headless, proxy_port, listener_fd=None):
        from aiohttp import web
        child_read, parent_write = os.pipe()
        parent_read, child_write = os.pipe()
        loop = asyncio.get_running_loop()
        self.reader = asyncio.StreamReader(limit=100 * 1024 * 1024)
        self.read_transport, _ = await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(self.reader),
            os.fdopen(parent_read, 'rb', buffering=0))
        transport, protocol = await loop.connect_write_pipe(asyncio.streams.FlowControlMixin,
            os.fdopen(parent_write, 'wb', buffering=0))
        self.writer = asyncio.StreamWriter(transport, protocol, None, loop)
        args = ['--remote-debugging-pipe', '--no-sandbox', '--no-first-run', '--no-default-browser-check',
                '--disable-background-networking', '--disable-component-update', '--disable-sync',
                '--disable-extensions', '--disable-popup-blocking', '--disable-dev-shm-usage',
                '--disable-gpu', '--disable-crashpad-for-testing', '--disable-quic',
                '--disable-crash-reporter', '--crash-dumps-dir=' + str(profile / 'Crashpad'),
                '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                '--use-mock-keychain', '--password-store=basic',
                '--user-data-dir=' + str(profile), '--proxy-server=http://127.0.0.1:' + str(proxy_port),
                '--proxy-bypass-list=<-loopback>']
        if headless:
            args.append('--headless=new')
        args.append('about:blank')
        try:
            self.process = await asyncio.create_subprocess_exec(sys.executable, '-I', str(Path(__file__).resolve()),
                '--chrome', str(child_read), str(child_write), executable, *args, pass_fds=(child_read, child_write),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        finally:
            os.close(child_read)
            os.close(child_write)
        self.stderr_task = asyncio.create_task(self.capture_stderr())
        self.reader_task = asyncio.create_task(self.read_pipe())
        try:
            await self.send({'method': 'Browser.getVersion'})
        except (ConnectionError, asyncio.TimeoutError) as exc:
            detail = self.stderr_tail.decode(errors='replace')
            raise ValueError(detail or 'browser pipe closed') from exc
        app = web.Application(client_max_size=32 * 1024 * 1024)
        app.router.add_get('/{token}', self.connect)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        server = (web.SockSite(self.runner, socket.socket(fileno=listener_fd)) if listener_fd is not None
                  else web.TCPSite(self.runner, '127.0.0.1', 0))
        await server.start()
        port = self.runner.addresses[0][1]
        self.endpoint = f'ws://127.0.0.1:{port}/{self.client_token}'
        self.owner_endpoint = f'ws://127.0.0.1:{port}/{self.owner_token}'
        return self.endpoint

    async def send(self, message):
        self.sequence += 1
        identifier = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[identifier] = future
        self.writer.write(json.dumps({**message, 'id': identifier}).encode() + b'\0')
        await self.writer.drain()
        try:
            return await asyncio.wait_for(future, 15)
        finally:
            self.pending.pop(identifier, None)

    async def read_pipe(self):
        try:
            while raw := await self.reader.readuntil(b'\0'):
                message = json.loads(raw[:-1])
                if 'id' in message:
                    future = self.pending.get(message['id'])
                    if future and not future.done():
                        future.set_result(message)
                    continue
                sid = message.get('sessionId')
                for client, state in list(self.clients.items()):
                    if sid not in state['sessions']:
                        continue
                    if message.get('method') == 'Target.attachedToTarget':
                        state['sessions'].add(message['params']['sessionId'])
                    forwarded = dict(message)
                    if sid == state['root']:
                        forwarded.pop('sessionId', None)
                    try:
                        await client.send_json(forwarded if state['owner'] else redact_headers(forwarded))
                    except ConnectionError:
                        continue
        except (asyncio.IncompleteReadError, ConnectionError):
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(ConnectionError('browser pipe closed'))

    async def connect(self, request):
        from aiohttp import web, WSMsgType
        token = request.match_info['token']
        owner = secrets.compare_digest(token, self.owner_token)
        if not owner and not secrets.compare_digest(token, self.client_token):
            raise web.HTTPForbidden()
        if request.headers.get('Origin'):
            raise web.HTTPForbidden()
        client = web.WebSocketResponse(max_msg_size=32 * 1024 * 1024)
        await client.prepare(request)
        attached = await self.send({'method': 'Target.attachToBrowserTarget'})
        root = attached['result']['sessionId']
        state = {'root': root, 'sessions': {root}, 'owner': owner}
        self.clients[client] = state
        tasks = set()
        async def forward(message):
            if message.get('method') == 'Browser.setDownloadBehavior':
                message = {**message, 'params': {k: v for k, v in message.get('params', {}).items() if k != 'downloadPath'}}
                message['params']['behavior'] = 'deny'
            sid = message.get('sessionId', root)
            if sid not in state['sessions'] or (not owner and not self.policy.allows_command(message)):
                await client.send_json({'id': message['id'], 'error': {'code': -32000, 'message': 'browser operation denied'},
                                        **({'sessionId': message['sessionId']} if 'sessionId' in message else {})})
                return
            result = await self.send({**message, 'sessionId': sid})
            result['id'] = message['id']
            if sid == root:
                result.pop('sessionId', None)
            await client.send_json(result if owner else redact_headers(result))
        try:
            async for event in client:
                if event.type != WSMsgType.TEXT:
                    continue
                message = json.loads(event.data)
                task = asyncio.create_task(forward(message))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.clients.pop(client, None)
            try:
                await self.send({'method': 'Target.detachFromTarget', 'params': {'sessionId': root}})
            except (ConnectionError, asyncio.TimeoutError):
                pass
        return client

    async def close(self):
        if self.process and self.process.returncode is None:
            try:
                await self.send({'method': 'Browser.close'})
                await asyncio.wait_for(self.process.wait(), 10)
            except (ConnectionError, asyncio.TimeoutError):
                self.process.kill()
                await self.process.wait()
        if self.runner:
            await self.runner.cleanup()
        if self.reader_task:
            self.reader_task.cancel()
            await asyncio.gather(self.reader_task, return_exceptions=True)
        if self.stderr_task:
            self.stderr_task.cancel()
            await asyncio.gather(self.stderr_task, return_exceptions=True)
        if getattr(self, 'writer', None):
            self.writer.close()
            self.read_transport.close()


if __name__ == '__main__' and sys.argv[1] == '--chrome':
    import fcntl
    descriptors = [fcntl.fcntl(int(value), fcntl.F_DUPFD, 5) for value in sys.argv[2:4]]
    for source, target in zip(descriptors, (3, 4)):
        os.dup2(source, target, inheritable=True)
        os.close(source)
    os.execv(sys.argv[4], sys.argv[4:])
