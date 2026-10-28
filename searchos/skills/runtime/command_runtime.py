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
    if not isinstance(argv, list) or len(argv) < 2 or any(not isinstance(a, str) or '\0' in a for a in argv):
        raise ValueError("argv must contain an interpreter and a skill script")
    if argv[0] not in _INTERPRETERS or argv[1].startswith('-'):
        raise ValueError("only python/python3, bash/sh, node and a script entry are allowed")
    script = (skill / argv[1]).resolve()
    if not _inside(script, skill) or not script.is_file():
        raise ValueError("entry must be a file inside the skill package")
    executable = sys.executable if argv[0] in {"python", "python3"} else shutil.which(argv[0])
    if not executable:
        raise ValueError(f"interpreter unavailable: {argv[0]}")
    # Python locates pyvenv.cfg through its invocation path; resolving the
    # interpreter symlink would silently switch to the base environment.
    return [os.path.abspath(executable), str(script), *argv[2:]]


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


def _environment(work: Path, *, network: bool = False, proxy_mode: str = 'inherit',
                 diagnostic_network_override: bool = False, network_audit: bool = False) -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
            "HOME": str(work), "TMPDIR": str(work), "LANG": "en_US.UTF-8",
            "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1"}
    if cache := _browser_cache():
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(cache)
    if network:
        from searchos.skills.runtime.network import proxy_environment
        env.update(proxy_environment(proxy_mode))
        if diagnostic_network_override:
            env['SEARCHOS_NETWORK_DIAGNOSTIC_MODE'] = proxy_mode
        if network_audit:
            env['SEARCHOS_NETWORK_AUDIT'] = '1'
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
             read_only_paths: tuple[Path, ...] = ()) -> tuple[list[str], str]:
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
        if _browser_cache():
            profile += (
                '(allow iokit-open (iokit-user-client-class "RootDomainUserClient"))'
                '(allow mach-register mach-lookup (global-name-regex '
                '#"^org[.]chromium[.]Chromium[.]MachPortRendezvousServer[.][0-9]+$"))'
                '(allow signal (target self) (target children))'
            )
        if network:
            profile += '(allow network*)(allow mach-lookup (global-name "com.apple.mDNSResponder"))(allow file-read* (literal "/private/etc/resolv.conf") (literal "/private/etc/hosts") (subpath "/private/etc/ssl"))'
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


async def run_command(skill_dir: Path, argv: list[str], *, work_dir: Path,
                      execution_dir: Path, stdin: str = '', timeout_s: float = 60,
                      network: bool = True, execution_id: str | None = None,
                      proxy_mode: str = 'inherit', diagnostic_network_override: bool = False,
                      network_audit: bool = False, read_only_paths=(), trace_functions: bool = False) -> dict:
    """认证浏览器由宿主提供有限能力；命令始终在原沙箱内执行。"""
    from searchos.skills.runtime.browser_auth import command_network_mode, command_profile, AuthRequired
    started_at = asyncio.get_running_loop().time()
    kwargs = dict(work_dir=work_dir, execution_dir=execution_dir, stdin=stdin,
                  timeout_s=timeout_s, network=network, execution_id=execution_id, proxy_mode=proxy_mode)
    if diagnostic_network_override:
        kwargs['diagnostic_network_override'] = True
    if network_audit:
        kwargs['network_audit'] = True
    if trace_functions:
        kwargs['trace_functions'] = True
    # Invalid commands must not open a login window or launch a browser.
    try:
        from searchos.skills.runtime.network import validate_proxy_mode, proxy_environment
        if (not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 300):
            raise ValueError('timeout must be between 0 and 300 seconds')
        validate_proxy_mode(proxy_mode)
        if network:
            proxy_environment(proxy_mode)  # Fail before opening a browser if no proxy exists.
        _entry(Path(skill_dir).resolve(), argv)
        allowed_reads = _read_only_paths(read_only_paths)
        if allowed_reads:
            work, records = (Path(path).resolve() for path in (work_dir, execution_dir))
            if any(_inside(a, b) or _inside(b, a)
                   for a in allowed_reads for b in (work, records)):
                raise ValueError('read-only paths must be separate from work and execution directories')
            kwargs['read_only_paths'] = allowed_reads
        profile = command_profile(Path(skill_dir), argv) if network else None
        browser_mode = proxy_mode
        if profile and not diagnostic_network_override:
            browser_mode = command_network_mode(Path(skill_dir), argv)
            proxy_environment(browser_mode)
    except (ValueError, OSError, TypeError) as exc:
        return {'status': 'blocked', 'error': str(exc), 'started': False,
                'exit_code': None, 'artifacts': [], 'stdout': '', 'stderr': ''}
    if not profile:
        return await _run_command(skill_dir, argv, **kwargs)
    execution_id = execution_id or ('exec-' + uuid.uuid4().hex)
    if (not isinstance(execution_id, str) or not execution_id or len(execution_id) > 100
            or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'
                   for c in execution_id)):
        return {'status': 'blocked', 'error': 'invalid execution id', 'started': False,
                'exit_code': None, 'artifacts': [], 'stdout': '', 'stderr': ''}
    kwargs['execution_id'] = execution_id
    record = Path(execution_dir).resolve() / execution_id / 'record.json'
    if record.parent.exists() or record.parent.is_symlink():
        return {'status': 'blocked', 'error': 'execution record already exists', 'started': False,
                'execution_id': execution_id, 'exit_code': None, 'artifacts': [],
                'stdout': '', 'stderr': ''}
    from searchos.skills.runtime.browser_broker import browser_bridge

    loop = asyncio.get_running_loop()
    deadline = started_at + timeout_s
    phase, receipt, owns_record = 'browser_prepare', None, False

    def observe_receipt(result, owned):
        nonlocal receipt, owns_record
        receipt, owns_record = result, owned

    async def lifecycle():
        nonlocal phase, receipt
        async with browser_bridge(profile, proxy_mode=browser_mode) as env:
            phase = 'command'
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError
            receipt = await _run_command(skill_dir, argv,
                **{**kwargs, 'timeout_s': remaining}, browser_env=env,
                _receipt_callback=observe_receipt)
            phase = 'browser_cleanup'

    task = asyncio.create_task(lifecycle())
    cancelled = timed_out = False
    timeout_phase = None
    try:
        done, _ = await asyncio.wait({task}, timeout=max(0, deadline - loop.time()))
        if not done:
            timed_out, timeout_phase = True, phase
            task.cancel()
    except asyncio.CancelledError:
        cancelled = True
        task.cancel()

    # 正常阶段共用期限；取消和超时后的资源释放最多再使用半秒。
    if not task.done():
        async def drain():
            grace_end = loop.time() + BROWSER_CLEANUP_GRACE_S
            done, _ = await asyncio.wait({task}, timeout=BROWSER_CLEANUP_GRACE_S * .8)
            if not done:
                task.cancel()
                await asyncio.wait({task}, timeout=max(0, grace_end - loop.time()))
        draining = asyncio.create_task(drain())
        while not draining.done():
            try:
                await asyncio.shield(draining)
            except asyncio.CancelledError:
                cancelled = True
        draining.result()
    failure = None
    if task.done():
        try:
            task.result()
        except BaseException as exc:
            failure = exc
    else:
        # 原生资源关闭有自己的取消边界；记录未完成清理，避免隐藏任务异常。
        task.add_done_callback(lambda completed: None if completed.cancelled()
                               else completed.exception())

    had_receipt = receipt is not None
    if receipt is None:
        receipt = {'execution_id': execution_id, 'status': 'blocked', 'started': False,
                   'exit_code': None, 'artifacts': [], 'stdout': '', 'stderr': ''}
        if isinstance(failure, AuthRequired):
            receipt.update(auth_required=True, error=str(failure))
        elif failure is not None and not isinstance(failure, asyncio.CancelledError):
            receipt['error'] = 'browser_unavailable: ' + type(failure).__name__

    cleanup_error = getattr(failure, 'cleanup_error', None)
    if had_receipt and failure is not None and not isinstance(failure, asyncio.CancelledError):
        cleanup_error = cleanup_error or 'browser_cleanup_failed: ' + type(failure).__name__
    if not task.done():
        cleanup_error = 'browser_cleanup_timeout: lifecycle did not stop within cleanup grace'
    if timed_out:
        receipt.update(timed_out=True, timeout_phase=timeout_phase)
        if receipt.get('status') not in {'completed', 'failed', 'timed_out'}:
            receipt['status'] = 'timed_out'
        if timeout_phase == 'browser_cleanup':
            cleanup_error = cleanup_error or 'browser_cleanup_timeout: call deadline exceeded'
    elif receipt.get('timed_out'):
        receipt.setdefault('timeout_phase', 'command')
    if isinstance(failure, asyncio.CancelledError) and not timed_out:
        cancelled = True
    if cancelled:
        receipt['cancelled'] = True
    if cleanup_error:
        receipt['cleanup_error'] = '; '.join(filter(None,
            [receipt.get('cleanup_error'), cleanup_error]))
    if owns_record and record.parent.is_dir() and not record.parent.is_symlink() and not record.is_symlink():
        temporary = record.with_name('record-browser-' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(record)
        except OSError as exc:
            receipt['record_error'] = type(exc).__name__
        finally:
            temporary.unlink(missing_ok=True)
    if cancelled:
        raise asyncio.CancelledError
    return receipt


async def _run_command(skill_dir: Path, argv: list[str], *, work_dir: Path,
                      execution_dir: Path, stdin: str = '', timeout_s: float = 60,
                      network: bool = True, execution_id: str | None = None,
                      browser_env: dict | None = None, proxy_mode: str = 'inherit',
                      diagnostic_network_override: bool = False, network_audit: bool = False,
                      _receipt_callback=None, read_only_paths=(), trace_functions: bool = False) -> dict:
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
        env = _environment(work, network=network, proxy_mode=proxy_mode,
                           diagnostic_network_override=diagnostic_network_override,
                           network_audit=network_audit)
        if browser_env:
            if set(browser_env) != {'SEARCHOS_BROWSER_URL', 'SEARCHOS_BROWSER_TOKEN'}:
                raise ValueError('unexpected browser capability environment')
            env.update(browser_env)
        allowed_reads = _read_only_paths(read_only_paths)
        trace_path = None
        if trace_functions and argv[0] in {'python', 'python3'}:
            trace_path = work / ('.function-trace-' + execution_id + '.json')
            command = [command[0], str(_FUNCTION_TRACE), str(trace_path), str(skill), argv[1], *argv[2:]]
            allowed_reads = (*allowed_reads, _FUNCTION_TRACE)
        if any(_inside(a, b) or _inside(b, a)
               for a in allowed_reads for b in (work, records)):
            raise ValueError('read-only paths must be separate from work and execution directories')
        marker = execution_id
        backend_options = {'read_only_paths': allowed_reads} if allowed_reads else {}
        command, backend = _backend([sys.executable, '-I', str(_LAUNCHER), str(marker), str(timeout_s), *command], skill, work, network, **backend_options)
        work.mkdir(parents=True, exist_ok=True)
        list(_files(work))
        record.mkdir(parents=True)
        if _receipt_callback:
            _receipt_callback(result, True)
    except (ValueError, OSError) as exc:
        result['error'] = str(exc)
        return result
    result['backend'] = backend
    result['capabilities'] = {'disk_quota': 'polled', 'process_cleanup': 'pid-namespace' if backend == 'bubblewrap' else 'process-group', 'memory_limit': False, 'process_count_limit': False, 'network': network, 'proxy_mode': proxy_mode}
    # Arguments/stdin may contain secrets: save only entry, counts and policy.
    (record / 'request.json').write_text(json.dumps({'entry': argv[:2], 'argument_count': len(argv)-2,
        'stdin_bytes': len(stdin.encode()), 'timeout_s': timeout_s, 'network': network, 'proxy_mode': proxy_mode,
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
                result['artifacts'] = _snapshot(work, record / 'artifacts')
            except (OSError, ValueError) as exc:
                result['artifact_error'] = str(exc)
                if result['status'] == 'completed':
                    result['status'] = 'failed'
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
