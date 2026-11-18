"""技能内 CLI 的隔离执行；后端缺失或被宿主禁止时不降级执行。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path
import shutil
import signal
import stat
import sys
import uuid

from searchos.network import network_scoped

OUTPUT_LIMIT = 16_000
LOG_LIMIT = 10_000_000
TAIL_LIMIT = 2_000
STDIN_LIMIT = 1_000_000
WORK_LIMIT = 100_000_000
FILE_LIMIT = 2_000
BROWSER_CLEANUP_GRACE_S = .5
_LAUNCHER = Path(__file__).with_name("_command_launcher.py").resolve()
_FUNCTION_TRACE = Path(__file__).with_name("_function_trace.py").resolve()
_INTERPRETERS = {"python", "python3", "bash", "sh", "node"}


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _entry(skill: Path, argv: list[str]) -> list[str]:
    if (not isinstance(argv, list) or not argv or not argv[0]
            or any(not isinstance(a, str) or '\0' in a for a in argv)):
        raise ValueError("argv must contain a command and optional arguments")
    local = skill / argv[0]
    executable = (sys.executable if argv[0] in {'python', 'python3'} else
                  str(local) if local.is_file() else shutil.which(argv[0]))
    if not executable:
        raise ValueError(f"command unavailable: {argv[0]}")
    arguments = list(argv[1:])
    if argv[0] in _INTERPRETERS and arguments and not arguments[0].startswith('-'):
        script = skill / arguments[0]
        if script.is_file():
            arguments[0] = str(script.resolve())
    # Python locates pyvenv.cfg through its invocation path; resolving the
    # interpreter symlink would silently switch to the base environment.
    return [os.path.abspath(executable), *arguments]


def _browser_cache() -> Path | None:
    """已安装的浏览器引擎是运行时依赖，不是用户浏览器资料目录。"""
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if configured and Path(configured).is_absolute():
        path = Path(configured)
    elif sys.platform == "darwin":
        path = Path.home() / "Library/Caches/ms-playwright"
    elif sys.platform.startswith("linux"):
        path = Path.home() / ".cache/ms-playwright"
    else:
        return None
    if path.is_dir() and not path.is_symlink():
        return path.resolve()
    return None


def _environment(work: Path, *, network: bool = False, network_policy=None) -> dict[str, str]:
    env = {"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
            "HOME": str(work), "TMPDIR": str(work), "LANG": "en_US.UTF-8",
            "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1"}
    if cache := _browser_cache():
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(cache)
    if network:
        from searchos.network import proxy_environment
        env.update(proxy_environment(policy=network_policy))
    return env


def _read_only_paths(paths) -> tuple[Path, ...]:
    """校验宿主授予的只读路径；拒绝符号链接和特殊文件。"""
    if not isinstance(paths, (tuple, list)):
        raise ValueError('read_only_paths must be a host-provided path sequence')
    validated = []
    aliases = {'/var': '/private/var', '/tmp': '/private/tmp', '/etc': '/private/etc'}
    for value in paths:
        if not isinstance(value, (str, os.PathLike)):
            raise ValueError('read-only paths must contain filesystem paths')
        path = Path(value)
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError('read-only paths must be absolute without parent traversal')
        for ancestor in (path, *path.parents):
            if ancestor.is_symlink() and not (
                sys.platform == 'darwin' and str(ancestor) in aliases
                and aliases[str(ancestor)] == str(ancestor.resolve())
            ):
                raise ValueError('read-only paths must not contain symbolic links')
        path = path.resolve(strict=True)
        if not path.is_file() and not path.is_dir():
            raise ValueError('read-only paths require regular files or directories')
        if path.is_dir():
            for base, directories, files in os.walk(path, followlinks=False):
                for name in [*directories, *files]:
                    item = Path(base) / name
                    mode = item.lstat().st_mode
                    if stat.S_ISLNK(mode):
                        raise ValueError('read-only directories must not contain symbolic links')
                    if not stat.S_ISDIR(mode) and not stat.S_ISREG(mode):
                        raise ValueError('read-only directories require regular files')
        validated.append(path)
    return tuple(dict.fromkeys(validated))


def _backend(command: list[str], skill: Path, work: Path, network: bool,
             read_only_paths: tuple[Path, ...] = (), *, browser_profile: Path | None = None,
             desktop: bool = False, network_ports: tuple[int, ...] | None = None,
             listen_loopback: bool = False, ipc_socket: Path | None = None) -> tuple[list[str], str]:
    if network_ports is not None and (not network or not network_ports or
            any(type(port) is not int or not 1 <= port <= 65535 for port in network_ports)):
        raise ValueError('invalid browser network capability')
    if network_ports is not None and sys.platform != 'darwin':
        raise ValueError('browser network isolation is unavailable on this platform')
    # Read only system runtimes, the selected Python environment and the package.
    roots = [Path(p) for p in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/System", "/Library/Frameworks", "/Library/Apple", "/opt/homebrew", sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix)]
    if cache := _browser_cache():
        roots.append(cache)
    roots = list(dict.fromkeys(p.resolve() for p in roots if p.exists()))
    # Parsers may consult system MIME tables outside the runtime directories.
    # Permit only existing table files, without opening their parent directories.
    for filename in mimetypes.knownfiles:
        path = Path(filename).resolve()
        if path.is_file() and not any(_inside(path, root) for root in roots):
            roots.append(path)
    if sys.platform == "darwin":
        sandbox = shutil.which("sandbox-exec")
        if not sandbox:
            raise ValueError("sandbox-exec unavailable")
        read = ' '.join(f'(subpath {json.dumps(str(p))})' for p in [*roots, skill, _LAUNCHER])
        read += ' ' + ' '.join(f'({"subpath" if p.is_dir() else "literal"} {json.dumps(str(p))})'
                               for p in read_only_paths)
        # macOS dyld opens the root directory node; this grants no child reads.
        profile = ('(version 1)(deny default)(allow process*)(allow sysctl-read)(allow file-read-data (literal "/"))'
                   '(allow mach-lookup (global-name "com.apple.system.logger") (global-name "com.apple.system.opendirectoryd.libinfo"))(allow file-read-metadata)'
                   f'(allow file-read* {read})'
                   f'(allow file-read* file-write* (subpath {json.dumps(str(work))}))'
                   '(allow file-read* file-write* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))')
        # Headless Chromium uses power monitoring and a PID-named rendezvous port.
        if _browser_cache() or browser_profile is not None:
            profile += (
                '(allow iokit-open (iokit-user-client-class "RootDomainUserClient"))'
                '(allow mach-register mach-lookup (global-name-regex '
                '#"^(org[.]chromium[.]Chromium|com[.]google[.]chrome[.]for[.]testing|com[.]google[.]Chrome)[.]MachPortRendezvousServer[.][0-9]+$"))'
                '(allow signal (target self) (target children))'
            )
        if network and network_ports is not None:
            profile += ''.join(f'(allow network-outbound (remote ip "localhost:{port}"))'
                               for port in network_ports)
            if listen_loopback:
                profile += '(allow network-inbound (local ip "localhost:*"))(allow network-bind (local ip "localhost:*"))'
                profile += (f'(allow network-bind network-inbound (local unix-socket (subpath {json.dumps(str(work))})))'
                            f'(allow network-outbound (remote unix-socket (subpath {json.dumps(str(work))})))')
            profile += ('(deny mach-lookup (global-name "com.apple.securityd")'
                        ' (global-name "com.apple.securityd.xpc") (global-name "com.apple.security.agent")'
                        ' (global-name "com.apple.SecurityServer"))')
        elif network:
            profile += '(allow network*)(allow mach-lookup (global-name "com.apple.mDNSResponder"))(allow file-read* (literal "/private/etc/resolv.conf") (literal "/private/etc/hosts") (subpath "/private/etc/ssl"))'
        if ipc_socket is not None:
            endpoint = json.dumps(str(ipc_socket))
            profile += f'(allow network-outbound (remote unix-socket (literal {endpoint})))(allow file-read* (literal {endpoint}))'
        if browser_profile is not None:
            profile += f'(allow file-read* file-write* (subpath {json.dumps(str(browser_profile))}))'
            profile += ('(deny mach-lookup (global-name "com.apple.securityd")'
                        ' (global-name "com.apple.securityd.xpc") (global-name "com.apple.security.agent")'
                        ' (global-name "com.apple.SecurityServer"))')
        if desktop:
            profile += ('(allow mach-lookup (global-name "com.apple.windowserver.active")'
                        ' (global-name "com.apple.CARenderServer")'
                        ' (global-name "com.apple.cfprefsd.agent") (global-name "com.apple.cfprefsd.daemon")'
                        ' (global-name "com.apple.dock.server") (global-name "com.apple.dock.fullscreen")'
                        ' (global-name "com.apple.windowmanager.server") (global-name "com.apple.tsm.portname"))'
                        '(allow mach-lookup (global-name "com.apple.coreservices.launchservicesd")'
                        ' (global-name "com.apple.lsd.mapdb") (global-name "com.apple.pasteboard.1")'
                        ' (global-name "com.apple.windowserver.session"))'
                        '(allow iokit-open (iokit-user-client-class "IOHIDParamUserClient")'
                        ' (iokit-user-client-class "IOSurfaceRootUserClient"))'
                        '(allow file-read* (subpath "/Library/Fonts"))'
                        '(allow mach-register (local-name-prefix "")'
                        ' (global-name-prefix "com.google.Chrome.apps.")'
                        ' (global-name-prefix "com.google.chrome.for.testing.apps."))'
                        '(allow ipc-posix-shm-read* (ipc-posix-name "apple.shm.notification_center")'
                        ' (ipc-posix-name-prefix "apple.cfprefs."))'
                        '(allow mach-lookup (global-name "com.apple.CodeSigningHelper")'
                        ' (global-name "com.apple.tccd") (global-name "com.apple.tccd.system")'
                        ' (global-name "com.apple.SafariPlatformSupport.Helper")'
                        ' (xpc-service-name "com.apple.SafariPlatformSupport.Helper")'
                        ' (xpc-service-name "com.apple.ViewBridgeAuxiliary"))')
        return [sandbox, '-p', profile, *command], 'sandbox-exec'
    if sys.platform.startswith('linux'):
        bwrap = shutil.which('bwrap')
        if not bwrap:
            raise ValueError('bubblewrap unavailable')
        args = [bwrap, '--die-with-parent', '--unshare-all']
        if network:
            args += ['--share-net']
        for root in [*roots, skill, _LAUNCHER, *read_only_paths]:
            args += ['--ro-bind', str(root), str(root)]
        for filename in ('/etc/resolv.conf', '/etc/hosts', '/etc/nsswitch.conf', '/etc/ssl'):
            if Path(filename).exists():
                args += ['--ro-bind', filename, filename]
        args += ['--proc', '/proc', '--dev', '/dev', '--bind', str(work), str(work), '--chdir', str(work), '--', *command]
        extra = []
        if ipc_socket is not None:
            extra += ['--ro-bind', str(ipc_socket), str(ipc_socket)]
        if browser_profile is not None:
            extra += ['--bind', str(browser_profile), str(browser_profile)]
        if desktop and Path('/tmp/.X11-unix').is_dir():
            extra += ['--ro-bind', '/tmp/.X11-unix', '/tmp/.X11-unix']
        if desktop and os.environ.get('XDG_RUNTIME_DIR') and os.environ.get('WAYLAND_DISPLAY'):
            socket = Path(os.environ['XDG_RUNTIME_DIR']) / os.environ['WAYLAND_DISPLAY']
            if socket.exists():
                extra += ['--ro-bind', str(socket), str(socket)]
        args[1:1] = extra
        return args, 'bubblewrap'
    raise ValueError('no supported OS isolation backend')


def _files(work: Path):
    count = size = 0
    for base, dirs, names in os.walk(work, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
        count += len(dirs)
        if count > FILE_LIMIT:
            raise ValueError('work directory quota exceeded')
        for name in names:
            path = Path(base) / name
            try:
                st = path.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(st.st_mode):
                continue
            count += 1
            size += st.st_size
            if count > FILE_LIMIT or size > WORK_LIMIT:
                raise ValueError('work directory quota exceeded')
            yield path


def _snapshot(work: Path, destination: Path) -> list[dict]:
    artifacts = []
    for path in _files(work):
        relative = path.relative_to(work)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # Do not follow a symlink substituted between traversal and open.
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            continue
        with os.fdopen(fd, 'rb') as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                continue
            with target.open('wb') as sink:
                digest = hashlib.sha256()
                total = 0
                while chunk := source.read(65536):
                    total += len(chunk)
                    if total > WORK_LIMIT:
                        raise ValueError('artifact quota exceeded')
                    digest.update(chunk)
                    sink.write(chunk)
        artifacts.append({'id': str(relative),
                          'path': str(relative), 'media_type': mimetypes.guess_type(str(relative))[0] or 'application/octet-stream',
                          'sha256': digest.hexdigest()})
    return artifacts


async def _kill(proc):
    # Even if the leader exited, children may still hold output pipes open.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    await proc.wait()


async def _capture_output(stream, name: str, record: Path, result: dict, execution_id: str):
    """分别记录有界预览、完整捕获日志及尾部诊断，显式标记日志超限。"""
    shown = bytearray()
    tail = bytearray()
    saved = seen = 0
    metadata = {'total_bytes': 0, 'saved_bytes': 0, 'preview_bytes': 0,
                'preview_truncated': False, 'log_truncated': False, 'log_path': f'{name}.log'}
    result.setdefault('streams', {})[name] = metadata
    prefix = ('SEARCHOS-STARTED:' + execution_id + '\n').encode()
    pending = b''
    checking_start = name == 'stderr'
    with (record / metadata['log_path']).open('wb') as output:
        def capture(data):
            nonlocal saved, seen
            seen += len(data)
            room = max(0, LOG_LIMIT - saved)
            output.write(data[:room])
            saved += min(room, len(data))
            shown.extend(data[:max(0, OUTPUT_LIMIT - len(shown))])
            tail.extend(data)
            if len(tail) > TAIL_LIMIT:
                del tail[:-TAIL_LIMIT]
            metadata.update(total_bytes=seen, saved_bytes=saved, preview_bytes=len(shown),
                            preview_truncated=seen > OUTPUT_LIMIT, log_truncated=seen > LOG_LIMIT)
            result[name] = shown.decode('utf-8', errors='replace')
            result[f'{name}_tail'] = tail.decode('utf-8', errors='replace')
            if seen > OUTPUT_LIMIT:
                result['truncated'] = True
            if seen > LOG_LIMIT:
                result.setdefault('error',
                    f'output_limit_exceeded: {name} exceeds {LOG_LIMIT} captured bytes')

        while data := await stream.read(65536):
            if checking_start:
                pending += data
                if len(pending) < len(prefix) and prefix.startswith(pending):
                    continue
                if pending.startswith(prefix):
                    result['started'] = True
                    data = pending[len(prefix):]
                else:
                    data = pending
                pending = b''
                checking_start = False
            capture(data)
        if pending:
            capture(pending)


@network_scoped
async def run_command(skill_dir: Path, argv: list[str], *, work_dir: Path,
                      execution_dir: Path, stdin: str = '', timeout_s: float = 60,
                      network: bool = True, execution_id: str | None = None,
                      read_only_paths=(), trace_functions: bool = False,
                      browser: bool = False, browser_request: dict | None = None,
                      runtime_env: dict | None = None, ipc_socket: Path | None = None,
                      wait_for_browser: bool = False, network_policy=None) -> dict:
    """创建任务持有浏览器；确认后探测返回调用方，CLI 至多重试一次。"""
    from searchos.skills.runtime.browser_session import BrowserSession, command_profile, current_session
    session, owned = current_session.get(), False
    kwargs = dict(work_dir=work_dir, execution_dir=execution_dir, stdin=stdin,
                  timeout_s=timeout_s, network=network, execution_id=execution_id)
    if runtime_env:
        kwargs['runtime_env'] = runtime_env
    if ipc_socket is not None:
        kwargs['ipc_socket'] = ipc_socket
    if network_policy is not None and network:
        kwargs['network_policy'] = network_policy
    if trace_functions:
        kwargs['trace_functions'] = True
    try:
        if not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 300:
            raise ValueError('timeout must be between 0 and 300 seconds')
        _entry(Path(skill_dir).resolve(), argv)
        reads = _read_only_paths(read_only_paths)
        if reads:
            work, records = (Path(path).resolve() for path in (work_dir, execution_dir))
            if any(_inside(a, b) or _inside(b, a) for a in reads for b in (work, records)):
                raise ValueError('read-only paths must be separate from work and execution directories')
            kwargs['read_only_paths'] = reads
        site = command_profile(Path(skill_dir), argv)
        if browser and not session:
            raise ValueError('browser probe requires a host-bound creation session')
        if (site or browser) and not network:
            raise ValueError('browser execution requires network access')
        if site and session and site != session.site:
            raise ValueError('browser profile host does not match this task')
        if site and session is None:
            session, owned = BrowserSession(site, **({'wait_timeout': timeout_s} if wait_for_browser else {})), True
    except (ValueError, OSError, TypeError) as exc:
        return {'status': 'blocked', 'error': str(exc), 'started': False,
                'exit_code': None, 'artifacts': [], 'stdout': '', 'stderr': ''}
    if not site and not browser:
        return await _run_command(skill_dir, argv, **kwargs)
    history = []
    request = browser_request or {'argv': argv, 'stdin': stdin}
    try:
        cached = session.blocked_requests.get(session.request_key(request))
        if cached:
            return {**{key: value for key, value in cached.items() if key != 'execution_id'},
                    'started': False, 'blocked_execution_id': cached.get('execution_id'),
                    'cached_external_block': True}
        while True:
            started = asyncio.get_running_loop().time()
            try:
                env = await asyncio.wait_for(session.ensure(), timeout_s)
                remaining = timeout_s - (asyncio.get_running_loop().time() - started)
                if remaining <= 0:
                    raise TimeoutError
                result = await _run_command(skill_dir, argv,
                    **{**kwargs, 'timeout_s': remaining}, browser_env=env, browser_session=session)
            except TimeoutError as exc:
                result = {'status': 'timed_out', 'timed_out': True, 'started': False,
                          'timeout_phase': 'browser_prepare',
                          'error': session.clean(f'browser_prepare: TimeoutError: {str(exc) or session.diagnostic or "等待浏览器准备超时"}'),
                          'exit_code': None, 'stdout': '', 'stderr': '', 'artifacts': []}
            except ConnectionError as exc:
                result = {'status': 'failed', 'error': session.clean(f'browser_prepare: {type(exc).__name__}: {exc}'),
                          'started': False, 'exit_code': None, 'stdout': '', 'stderr': '', 'artifacts': []}
            except (ValueError, OSError) as exc:
                result = {'status': 'blocked', 'error': session.clean(str(exc)), 'external_blocked': True,
                          'next_action': 'wait_external', 'started': False, 'exit_code': None,
                          'stdout': '', 'stderr': '', 'artifacts': []}
            result['browser_mode'] = session.mode
            retry, resolved = await session.resolve(result, request, after_confirmation=bool(history))
            if result.get('execution_id'):
                receipt = Path(execution_dir) / result['execution_id'] / 'record.json'
                receipt.write_text(json.dumps(resolved, ensure_ascii=False, indent=2))
            if not retry:
                return {**resolved, **({'previous_executions': history} if history else {})}
            history.append(resolved)
            kwargs['execution_id'] = None
    finally:
        if owned:
            cleanup = asyncio.create_task(session.close())
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            cleanup.result()


def _redact_browser_execution(result, session, execution_dir, work_dir):
    """在回执、日志与分发产物可见前清除会话信息。"""
    roots = [Path(work_dir)]
    if result.get('execution_id'):
        roots.append(Path(execution_dir) / result['execution_id'])
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob('*'):
            if not path.is_file() or path.is_symlink():
                continue
            data = path.read_bytes()
            try:
                value = data.decode('utf-8')
            except UnicodeError:
                if any(secret.encode() in data for secret in session.secrets if len(secret) >= 4):
                    path.unlink()
                continue
            cleaned = session.clean(value)
            if cleaned != value:
                path.write_text(cleaned, encoding='utf-8')
    result = session.clean(result)
    return result


async def _run_command(skill_dir: Path, argv: list[str], *, work_dir: Path,
                      execution_dir: Path, stdin: str = '', timeout_s: float = 60,
                      network: bool = True, execution_id: str | None = None,
                      browser_env: dict | None = None,
                      _receipt_callback=None, read_only_paths=(), trace_functions: bool = False,
                      browser_session=None, runtime_env=None, ipc_socket=None, network_policy=None) -> dict:
    """返回一次命令记录；取消时保存 cancelled 记录并重新抛出 CancelledError。

    execution_dir/<execution_id>/record.json、非空日志及 artifacts/。
    任务调用方须串行使用同一 work_dir；运行目录与技能目录不得互相包含。
    工作目录配额采用轮询限制，不能替代文件系统硬配额。
    """
    execution_id = execution_id or ('exec-' + uuid.uuid4().hex)
    if any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in execution_id) or len(execution_id) > 100:
        raise ValueError('invalid execution id')
    result = dict(execution_id=execution_id, status='blocked', exit_code=None,
                  stdout='', stderr='', truncated=False, artifacts=[], started=False, timed_out=False)
    if browser_session is not None:
        result['browser_mode'] = browser_session.mode
    from searchos.network import current_context
    network_context = current_context()
    event_cursor = network_context.event_cursor
    if _receipt_callback:
        _receipt_callback(result, False)
    skill, work, records = (Path(p).resolve() for p in (skill_dir, work_dir, execution_dir))
    record = records / execution_id
    try:
        if any(_inside(a, b) or _inside(b, a) for a, b in ((skill, work), (skill, records), (work, records))):
            raise ValueError('skill, work and execution directories must be disjoint')
        if not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 300:
            raise ValueError('timeout must be between 0 and 300 seconds')
        if not isinstance(stdin, str) or len(stdin.encode()) > STDIN_LIMIT:
            raise ValueError('stdin exceeds limit or is not text')
        command = _entry(skill, argv)
        env = _environment(work, network=network,
                           network_policy=getattr(browser_session, 'network_policy', None) or network_policy)
        env.update(SKILL_DIR=str(skill), PYTHONPATH=str(skill))
        if runtime_env:
            allowed = {'SEARCHOS_BRIDGE_SOCKET', 'SEARCHOS_INPUTS_FILE', 'SEARCHOS_RUN_TOKEN'}
            if set(runtime_env) - allowed or any(not isinstance(v, str) for v in runtime_env.values()):
                raise ValueError('invalid runtime environment')
            env.update(runtime_env)
        if browser_env:
            if set(browser_env) != {'BROWSER_CDP_URL'}:
                raise ValueError('unexpected browser capability environment')
            env.update(browser_env)
            bypass = ','.join(filter(None, [env.get('NO_PROXY', ''), 'localhost', '127.0.0.1', '::1']))
            env['NO_PROXY'] = env['no_proxy'] = bypass
        allowed_reads = _read_only_paths(read_only_paths)
        trace_path = None
        if (trace_functions and len(argv) > 1 and argv[0] in {'python', 'python3'}
                and not argv[1].startswith('-') and (skill / argv[1]).resolve().is_relative_to(skill)
                and (skill / argv[1]).is_file()):
            trace_path = work / ('.function-trace-' + execution_id + '.json')
            command = [command[0], str(_FUNCTION_TRACE), str(trace_path), str(skill), argv[1], *argv[2:]]
            allowed_reads = (*allowed_reads, _FUNCTION_TRACE)
        if any(_inside(a, b) or _inside(b, a)
               for a in allowed_reads for b in (work, records)):
            raise ValueError('read-only paths must be separate from work and execution directories')
        marker = execution_id
        backend_options = {'read_only_paths': allowed_reads} if allowed_reads else {}
        if ipc_socket is not None:
            ipc_socket = Path(ipc_socket)
            if ipc_socket.is_symlink() or not ipc_socket.is_socket():
                raise ValueError('invalid execution bridge socket')
            backend_options['ipc_socket'] = ipc_socket.resolve()
        if browser_env:
            from urllib.parse import urlsplit
            endpoint = urlsplit(browser_env['BROWSER_CDP_URL'])
            if endpoint.scheme != 'ws' or endpoint.hostname != '127.0.0.1' or not endpoint.port or len(endpoint.path) < 32:
                raise ValueError('browser capability requires an authenticated local gateway')
            proxy = urlsplit(env['HTTPS_PROXY'])
            backend_options['network_ports'] = tuple(dict.fromkeys((endpoint.port, proxy.port)))
        elif network_policy is not None and network:
            from urllib.parse import urlsplit
            backend_options['network_ports'] = (urlsplit(env['HTTPS_PROXY']).port,)
        command, backend = _backend([sys.executable, '-I', str(_LAUNCHER), str(marker), str(timeout_s), *command], skill, work, network, **backend_options)
        work.mkdir(parents=True, exist_ok=True)
        before_files = {str(path.relative_to(work)): (path.stat().st_mtime_ns, path.stat().st_ctime_ns, path.stat().st_size)
                        for path in _files(work)}
        record.mkdir(parents=True)
        if _receipt_callback:
            _receipt_callback(result, True)
    except (ValueError, OSError) as exc:
        result['error'] = str(exc)
        return result
    result['backend'] = backend
    result['capabilities'] = {'disk_quota': 'polled', 'process_cleanup': 'pid-namespace' if backend == 'bubblewrap' else 'process-group', 'memory_limit': False, 'process_count_limit': False, 'network': network}
    result['network'] = {'config_fingerprint': network_context.config.fingerprint,
                         'route_generation': network_context.store.generation,
                         'scope': 'task', 'connections': []}
    # 参数和 stdin 可能包含凭据，仅保存程序名、数量与执行策略。
    (record / 'request.json').write_text(json.dumps({'entry': argv[:1], 'argument_count': len(argv)-1,
        'stdin_bytes': len(stdin.encode()), 'timeout_s': timeout_s, 'network': network,
        'network_fingerprint': network_context.config.fingerprint,
        'read_only_paths': [str(path) for path in allowed_reads]}))
    proc = None
    tasks = []
    cancelled = False
    cleanup_task = None

    async def cleanup():
        nonlocal cleanup_task
        if cleanup_task is None:
            cleanup_task = asyncio.create_task(_kill(proc))
        # 取消继续等待本次清理，避免再次向已回收的进程组发信号。
        await asyncio.shield(cleanup_task)

    async def feed():
        try:
            proc.stdin.write(stdin.encode())
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            proc.stdin.close()

    async def monitor():
        while proc.returncode is None:
            if any(stream['log_truncated'] for stream in result.get('streams', {}).values()):
                raise ValueError(result['error'])
            list(_files(work))
            await asyncio.sleep(.1)

    try:
        proc = await asyncio.create_subprocess_exec(*command, cwd=work, env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True)
        tasks = [asyncio.create_task(_capture_output(proc.stdout, 'stdout', record, result, execution_id)),
                 asyncio.create_task(_capture_output(proc.stderr, 'stderr', record, result, execution_id)),
                 asyncio.create_task(feed()), asyncio.create_task(monitor())]
        async def wait_leader():
            # Process.wait also waits for inherited pipes; terminate descendants
            # as soon as the leader exits, before waiting for those pipes.
            while proc.returncode is None:
                await asyncio.sleep(.01)

        async def finish():
            waiter = asyncio.create_task(wait_leader())
            try:
                done, _ = await asyncio.wait([waiter, tasks[-1]], return_when=asyncio.FIRST_COMPLETED)
                if tasks[-1] in done:
                    tasks[-1].result()
                await waiter
                await cleanup()
                await asyncio.gather(*tasks)
            finally:
                if not waiter.done():
                    waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
        await asyncio.wait_for(finish(), timeout_s)
        result['exit_code'] = proc.returncode
        result['status'] = 'completed' if proc.returncode == 0 else 'failed'
        if not result['started'] and ('sandbox_apply:' in result['stderr'] or (backend == 'bubblewrap' and 'bwrap:' in result['stderr'])):
            result['status'] = 'blocked'
            result['error'] = 'OS isolation backend could not start: ' + result['stderr'][:2000]
    except asyncio.CancelledError:
        cancelled = True
        result['status'] = 'cancelled'
    except TimeoutError:
        result['status'] = 'timed_out'
        result['timed_out'] = True
        result['timeout_phase'] = 'execution'
    except (OSError, ValueError) as exc:
        result['status'] = 'failed' if proc else 'blocked'
        result.setdefault('error', str(exc))
    finally:
        # 单独完成回收和落盘，重复取消仍等待同一份本次回执。
        async def finalize():
            if proc:
                try:
                    await cleanup()
                except OSError as exc:
                    if proc.returncode is None:
                        raise
                    result['cleanup_error'] = 'process_group_cleanup_failed: ' + str(exc)
                    if result['status'] == 'completed':
                        result['status'] = 'failed'
                result['exit_code'] = proc.returncode
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if (result['status'] == 'completed'
                    and any(stream['log_truncated'] for stream in result.get('streams', {}).values())):
                result['status'] = 'failed'
            if trace_path is not None:
                try:
                    if trace_path.is_symlink() or trace_path.stat().st_size > LOG_LIMIT:
                        raise ValueError('invalid function trace')
                    result['function_trace'] = json.loads(trace_path.read_text(encoding='utf-8'))
                    (record / 'function-trace.json').write_text(json.dumps(result['function_trace']))
                except (OSError, ValueError):
                    result['function_trace'] = {'complete': False, 'calls': []}
                finally:
                    trace_path.unlink(missing_ok=True)
            try:
                result['updated_files'] = [str(path.relative_to(work)) for path in _files(work)
                    if before_files.get(str(path.relative_to(work))) !=
                    (path.stat().st_mtime_ns, path.stat().st_ctime_ns, path.stat().st_size)]
            except (OSError, ValueError) as exc:
                result.update(artifact_error=str(exc), updated_files=[])
                if result['status'] == 'completed':
                    result['status'] = 'failed'
            if browser_session:
                try:
                    await browser_session.refresh_secrets()
                except Exception as exc:
                    result['cleanup_error'] = 'browser_state_unavailable: ' + browser_session.clean(
                        f'{type(exc).__name__}: {exc}')
                clean = _redact_browser_execution(result, browser_session, execution_dir, work_dir)
                result.clear()
                result.update(clean)
            try:
                result['artifacts'] = _snapshot(work, record / 'artifacts')
            except (OSError, ValueError) as exc:
                result['artifact_error'] = str(exc)
                if result['status'] == 'completed':
                    result['status'] = 'failed'
            result['network']['connections'] = network_context.events_since(event_cursor)
            (record / 'record.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
            for name in ('stdout', 'stderr'):
                log = record / f'{name}.log'
                if log.is_file() and log.stat().st_size == 0:
                    log.unlink()
        finalizing = asyncio.create_task(finalize())
        while not finalizing.done():
            try:
                await asyncio.shield(finalizing)
            except asyncio.CancelledError:
                cancelled = True
                if result['status'] not in {'completed', 'failed', 'timed_out'}:
                    result['status'] = 'cancelled'
        finalizing.result()
    if cancelled:
        raise asyncio.CancelledError
    return result
