"""HTTP 转发与 CONNECT 隧道；在转发业务字节之前选择线路。"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
import ssl
import time
from urllib.parse import unquote, urlsplit

import h11


class NetworkFailure(OSError):
    def __init__(self, phase: str, message: str = ''):
        self.phase = phase
        super().__init__(message or phase)


class DestinationPolicy:
    bypass_loopback = True

    def __init__(self, allowed_urls=()):
        self.local_origins = frozenset((p.hostname, p.port or (443 if p.scheme == 'https' else 80))
                                      for url in allowed_urls if (p := urlsplit(url)).hostname)

    def allows_host(self, host):
        return bool(host)

    def allows_port(self, host, port):
        return 1 <= port <= 65535

    def allows_private(self, host, port):
        return (host, port) in self.local_origins


class NetworkProxy:
    def __init__(self, policy, *, context):
        self.policy = policy
        self.context = context
        self.server = None
        self.connections = set()

    async def start(self):
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', 0, limit=65536)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def addresses(self, host, port):
        try:
            rows = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise NetworkFailure('dns') from exc
        private = getattr(self.policy, 'allows_private', lambda h, p: False)(host, port)
        if not rows or (not private and any(
                not ipaddress.ip_address(r[4][0]).is_global for r in rows)):
            raise NetworkFailure('destination_denied')
        return rows

    async def open_remote(self, address, port, family, route=None):
        route = route or ('proxy' if self.context.config.proxy_url else 'direct')
        if route == 'direct':
            try:
                return await asyncio.open_connection(address, port, family=family)
            except OSError as exc:
                raise NetworkFailure('target_connect') from exc
        proxy = urlsplit(self.context.config.proxy_url)
        if not proxy.hostname:
            raise NetworkFailure('proxy_connect', 'proxy_unavailable')
        writer = None
        try:
            reader, writer = await asyncio.open_connection(proxy.hostname,
                proxy.port or (1080 if proxy.scheme.startswith('socks')
                               else 443 if proxy.scheme == 'https' else 80),
                ssl=proxy.scheme == 'https')
            if proxy.scheme.startswith('socks'):
                auth = proxy.username is not None
                writer.write(b'\x05\x01' + (b'\x02' if auth else b'\x00'))
                await writer.drain()
                if await reader.readexactly(2) != b'\x05' + (b'\x02' if auth else b'\x00'):
                    raise NetworkFailure('proxy_auth' if auth else 'proxy_connect')
                if auth:
                    user, password = (unquote(proxy.username).encode(),
                                      unquote(proxy.password or '').encode())
                    if len(user) > 255 or len(password) > 255:
                        raise NetworkFailure('proxy_auth')
                    writer.write(b'\x01' + bytes([len(user)]) + user
                                 + bytes([len(password)]) + password)
                    await writer.drain()
                    if await reader.readexactly(2) != b'\x01\x00':
                        raise NetworkFailure('proxy_auth')
                ip = ipaddress.ip_address(address)
                writer.write(b'\x05\x01\x00' + (b'\x01' if ip.version == 4 else b'\x04')
                             + ip.packed + port.to_bytes(2, 'big'))
                await writer.drain()
                reply = await reader.readexactly(4)
                if reply[:2] != b'\x05\x00':
                    raise NetworkFailure('target_connect')
                if reply[3] == 1:
                    await reader.readexactly(6)
                elif reply[3] == 4:
                    await reader.readexactly(18)
                elif reply[3] == 3:
                    await reader.readexactly((await reader.readexactly(1))[0] + 2)
                else:
                    raise NetworkFailure('proxy_connect')
            else:
                target = f'[{address}]:{port}' if ':' in address else f'{address}:{port}'
                authorization = ''
                if proxy.username is not None:
                    credentials = (f'{unquote(proxy.username)}:'
                                   f'{unquote(proxy.password or "")}').encode()
                    authorization = ('Proxy-Authorization: Basic '
                                     + base64.b64encode(credentials).decode() + '\r\n')
                writer.write(
                    f'CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n{authorization}\r\n'.encode())
                await writer.drain()
                header = await reader.readuntil(b'\r\n\r\n')
                code = header.split(b' ', 2)[1]
                if code != b'200':
                    raise NetworkFailure('proxy_auth' if code == b'407' else 'proxy_connect')
            return reader, writer
        except BaseException as exc:
            if writer:
                writer.close()
            if isinstance(exc, ssl.SSLCertVerificationError):
                raise NetworkFailure('tls_certificate') from exc
            if isinstance(exc, (NetworkFailure, asyncio.CancelledError)):
                raise
            raise NetworkFailure('proxy_connect') from exc

    async def connect(self, host, port, *, forced_route=None, timeout=15):
        """同目标串行选线；只把成功的备用连接记为待确认。"""
        if (not self.policy.allows_host(host) or not getattr(
                self.policy, 'allows_port', lambda h, p: p in (80, 443))(host, port)):
            raise NetworkFailure('destination_denied')
        deadline = asyncio.get_running_loop().time() + timeout
        key = (host, port)
        lock = self.context.connection_locks.setdefault(key, asyncio.Lock())
        async with asyncio.timeout_at(deadline):
            async with lock:
                addresses = await self.addresses(host, port)
                route, source = self.context.select(host, port)
                generation = self.context.store.generation
                if forced_route:
                    route, source = forced_route, 'diagnostic'
                elif (getattr(self.policy, 'bypass_loopback', False)
                        and not self.context.config.manual_route(host)
                        and all(ipaddress.ip_address(row[4][0]).is_loopback for row in addresses)):
                    route, source = 'direct', 'local'
                choices = [route]
                if not forced_route and source != 'local' and self.context.can_switch(host, port):
                    choices.append('direct' if route == 'proxy' else 'proxy')
                for index, selected in enumerate(choices):
                    if index:
                        self.context.attempted.add(key)
                    started = time.monotonic()
                    failure = None
                    for family, _, _, _, address in addresses:
                        remaining = deadline - asyncio.get_running_loop().time()
                        # 留出一次备用建连时间；整个过程共用原期限。
                        allowance = remaining / (2 if index == 0 and len(choices) > 1 else 1)
                        try:
                            incoming, outgoing = await asyncio.wait_for(
                                self.open_remote(address[0], port, family, selected),
                                max(.001, allowance))
                            self.context.record(
                                host, port, selected, source if not index else 'fallback',
                                'connected', time.monotonic() - started)
                            if index:
                                self.context.stage_route(host, port, selected, generation)
                            return incoming, outgoing, selected
                        except (OSError, TimeoutError, asyncio.IncompleteReadError) as exc:
                            failure = exc
                    phase = getattr(failure, 'phase', 'target_connect')
                    self.context.record(host, port, selected, source if not index else 'fallback',
                                        phase, time.monotonic() - started)
                    if phase in {'destination_denied', 'proxy_auth', 'tls_certificate'}:
                        raise failure
                raise failure or NetworkFailure('target_connect')

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.connections.add(task)
        remote, established = None, False
        try:
            header = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 15)
            method, target, version = header.split(b'\r\n', 1)[0].decode('ascii').split(' ', 2)
            value = urlsplit('https://' + target if method == 'CONNECT' else target)
            host = (value.hostname or '').lower().rstrip('.')
            port = value.port or (443 if method == 'CONNECT' else 80)
            if (value.username or value.password or not host
                    or version not in {'HTTP/1.0', 'HTTP/1.1'}
                    or (method != 'CONNECT' and value.scheme not in {'http', 'ws'})):
                raise NetworkFailure('destination_denied')
            incoming, remote, route = await self.connect(host, port)
            if method == 'CONNECT':
                writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                await writer.drain()
                established = True
            else:
                request_parser = h11.Connection(h11.SERVER)
                request_parser.receive_data(header)
                if not isinstance(request_parser.next_event(), h11.Request):
                    raise NetworkFailure('destination_denied')
                path = value.path or '/'
                if value.query:
                    path += '?' + value.query
                lines = header.split(b'\r\n')[1:]
                lines = [line for line in lines if not line.lower().startswith(
                    (b'proxy-authorization:', b'proxy-connection:', b'connection:', b'host:'))]
                # 一条明文代理连接只服务一个请求，后续目标重新执行策略检查。
                authority = f'[{host}]' if ':' in host else host
                authority += f':{port}' if port != 80 else ''
                upgrade = any(line.lower().startswith(b'upgrade:') for line in lines)
                prefix = [f'{method} {path} {version}'.encode(), f'Host: {authority}'.encode(),
                          b'Connection: Upgrade' if upgrade else b'Connection: close']
                request_sender = h11.Connection(h11.CLIENT)
                forwarded_headers = [tuple(line.split(b':', 1))
                                     for line in (prefix + lines)[1:] if line]
                remote.write(request_sender.send(h11.Request(method=method, target=path,
                    headers=[(k, v.strip()) for k, v in forwarded_headers])))
                await remote.drain()
                established = True

            async def upload():
                if method != 'CONNECT' and not upgrade:
                    while True:
                        event = request_parser.next_event()
                        if event is h11.NEED_DATA:
                            block = await reader.read(65536)
                            request_parser.receive_data(block)
                        elif isinstance(event, (h11.Data, h11.EndOfMessage)):
                            remote.write(request_sender.send(event))
                            await remote.drain()
                            if isinstance(event, h11.EndOfMessage):
                                if await reader.read(1):
                                    raise NetworkFailure('request_pipelining')
                                if remote.can_write_eof():
                                    remote.write_eof()
                                else:
                                    remote.close()
                                return
                        elif isinstance(event, h11.ConnectionClosed):
                            return
                while chunk := await reader.read(65536):
                    remote.write(chunk)
                    await remote.drain()
                if remote.can_write_eof():
                    remote.write_eof()
                else:
                    remote.close()

            async def download():
                if method != 'CONNECT':
                    response = await incoming.readuntil(b'\r\n\r\n')
                    try:
                        status = int(response.split(b' ', 2)[1])
                        self.context.confirm_url(target, status)
                    except (ValueError, IndexError):
                        pass
                    writer.write(response)
                    await writer.drain()
                while chunk := await incoming.read(65536):
                    writer.write(chunk)
                    await writer.drain()

            pumps = [asyncio.create_task(upload()), asyncio.create_task(download())]
            try:
                done, _ = await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
                # 客户端半关闭写端仍允许服务端送回完整响应。
                if pumps[0] in done and pumps[0].exception() is None:
                    await pumps[1]
                else:
                    for completed in done:
                        completed.result()
            finally:
                for pump in pumps:
                    pump.cancel()
                await asyncio.gather(*pumps, return_exceptions=True)
        except (ValueError, OSError, h11.ProtocolError, TimeoutError,
                asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
            if not established:
                phase = getattr(exc, 'phase', 'target_connect')
                code = ('403 Forbidden' if phase == 'destination_denied'
                        else '504 Gateway Timeout' if isinstance(exc, TimeoutError)
                        else '502 Bad Gateway')
                body = phase.encode()
                writer.write((f'HTTP/1.1 {code}\r\nConnection: close\r\n'
                              f'Content-Length: {len(body)}\r\n'
                              f'X-SearchOS-Network-Error: {phase}\r\n\r\n').encode() + body)
        finally:
            if remote:
                remote.close()
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            self.connections.discard(task)

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        tasks = list(self.connections)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
