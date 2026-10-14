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
LOG_LIMIT = 1_000_000
WORK_LIMIT = 100_000_000
FILE_LIMIT = 2_000
_LAUNCHER = Path(__file__).with_name("_command_launcher.py").resolve()
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
    return [str(Path(executable).resolve()), str(script), *argv[2:]]


def _browser_cache() -> Path | None:
    """已安装的浏览器引擎是运行时依赖，不是用户浏览器资料目录。"""
    if sys.platform == "darwin":
        path = Path.home() / "Library/Caches/ms-playwright"
    elif sys.platform.startswith("linux"):
        path = Path.home() / ".cache/ms-playwright"
    else:
        return None
    if path.is_dir() and not path.is_symlink():
        return path.resolve()
    return None


def _environment(work: Path, *, network: bool = False, proxy_mode: str = 'inherit') -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin",
            "HOME": str(work), "TMPDIR": str(work), "LANG": "en_US.UTF-8",
            "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1"}
    if cache := _browser_cache():
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(cache)
    if network:
        from searchos.skills.runtime.network import proxy_environment
        env.update(proxy_environment(proxy_mode))
    return env


def _backend(command: list[str], skill: Path, work: Path, network: bool) -> tuple[list[str], str]:
    # Read only system runtimes, the selected Python environment and the package.
    roots = [Path(p) for p in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/System", "/Library/Frameworks", "/Library/Apple", "/opt/homebrew", sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix)]
    if cache := _browser_cache():
        roots.append(cache)
    roots = list(dict.fromkeys(p.resolve() for p in roots if p.exists()))
    if sys.platform == "darwin":
        sandbox = shutil.which("sandbox-exec")
        if not sandbox:
            raise ValueError("sandbox-exec unavailable")
        read = ' '.join(f'(subpath {json.dumps(str(p))})' for p in [*roots, skill, _LAUNCHER])
        # macOS dyld opens the root directory node; this grants no child reads.
        profile = ('(version 1)(deny default)(allow process*)(allow sysctl-read)(allow file-read-data (literal "/"))'
                   '(allow mach-lookup (global-name "com.apple.system.logger") (global-name "com.apple.system.opendirectoryd.libinfo"))(allow file-read-metadata)'
                   f'(allow file-read* {read})'
                   f'(allow file-read* file-write* (subpath {json.dumps(str(work))}))'
                   '(allow file-read* file-write* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))')
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
        for root in [*roots, skill, _LAUNCHER]:
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
            st = path.lstat()
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
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
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


async def run_command(skill_dir: Path, argv: list[str], *, work_dir: Path,
                      execution_dir: Path, stdin: str = '', timeout_s: float = 60,
                      network: bool = True, execution_id: str | None = None,
                      proxy_mode: str = 'inherit') -> dict:
    """认证浏览器由宿主提供有限能力；命令始终在原沙箱内执行。"""
    from searchos.skills.runtime.browser_auth import command_profile, AuthRequired
    kwargs = dict(work_dir=work_dir, execution_dir=execution_dir, stdin=stdin,
                  timeout_s=timeout_s, network=network, execution_id=execution_id, proxy_mode=proxy_mode)
    # Invalid commands must not open a login window or launch a browser.
    try:
        from searchos.skills.runtime.network import validate_proxy_mode, proxy_environment
        validate_proxy_mode(proxy_mode)
        if network:
            proxy_environment(proxy_mode)  # Fail before opening a browser if no proxy exists.
        _entry(Path(skill_dir).resolve(), argv)
        profile = command_profile(Path(skill_dir), argv) if network else None
    except (ValueError, OSError, TypeError) as exc:
        return {'status': 'blocked', 'error': str(exc), 'started': False,
                'exit_code': None, 'artifacts': [], 'stdout': '', 'stderr': ''}
    if not profile:
        return await _run_command(skill_dir, argv, **kwargs)
    try:
        from searchos.skills.runtime.browser_broker import browser_bridge
        async with browser_bridge(profile, proxy_mode=proxy_mode) as env:
            return await _run_command(skill_dir, argv, **kwargs, browser_env=env)
    except AuthRequired as exc:
        return {'status': 'blocked', 'error': str(exc), 'auth_required': True,
                'started': False, 'exit_code': None, 'artifacts': [], 'stdout': '', 'stderr': ''}
    except Exception:
        return {'status': 'blocked', 'error': 'browser_unavailable: 无法启动宿主认证浏览器，请检查 Playwright/Chromium 和本机桌面。',
                'started': False, 'exit_code': None, 'artifacts': [], 'stdout': '', 'stderr': ''}


async def _run_command(skill_dir: Path, argv: list[str], *, work_dir: Path,
                      execution_dir: Path, stdin: str = '', timeout_s: float = 60,
                      network: bool = True, execution_id: str | None = None,
                      browser_env: dict | None = None, proxy_mode: str = 'inherit') -> dict:
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
    skill, work, records = (Path(p).resolve() for p in (skill_dir, work_dir, execution_dir))
    record = records / execution_id
    try:
        if any(_inside(a, b) or _inside(b, a) for a, b in ((skill, work), (skill, records), (work, records))):
            raise ValueError('skill, work and execution directories must be disjoint')
        if not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 300:
            raise ValueError('timeout must be between 0 and 300 seconds')
        if not isinstance(stdin, str) or len(stdin.encode()) > LOG_LIMIT:
            raise ValueError('stdin exceeds limit or is not text')
        command = _entry(skill, argv)
        env = _environment(work, network=network, proxy_mode=proxy_mode)
        if browser_env:
            if set(browser_env) != {'SEARCHOS_BROWSER_URL', 'SEARCHOS_BROWSER_TOKEN'}:
                raise ValueError('unexpected browser capability environment')
            env.update(browser_env)
        marker = execution_id
        command, backend = _backend([sys.executable, '-I', str(_LAUNCHER), str(marker), str(timeout_s), *command], skill, work, network)
        work.mkdir(parents=True, exist_ok=True)
        list(_files(work))
        record.mkdir(parents=True)
    except (ValueError, OSError) as exc:
        result['error'] = str(exc)
        return result
    result['backend'] = backend
    result['capabilities'] = {'disk_quota': 'polled', 'process_cleanup': 'pid-namespace' if backend == 'bubblewrap' else 'process-group', 'memory_limit': False, 'process_count_limit': False, 'network': network, 'proxy_mode': proxy_mode}
    # Arguments/stdin may contain secrets: save only entry, counts and policy.
    (record / 'request.json').write_text(json.dumps({'entry': argv[:2], 'argument_count': len(argv)-2,
        'stdin_bytes': len(stdin.encode()), 'timeout_s': timeout_s, 'network': network, 'proxy_mode': proxy_mode}))
    proc = None
    tasks = []
    cancelled = False

    async def drain(stream, name):
        shown = bytearray()
        saved = 0
        seen = 0
        prefix = ('SEARCHOS-STARTED:' + execution_id + '\n').encode()
        pending = b''
        checking_start = name == 'stderr'
        with (record / f'{name}.log').open('wb') as output:
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
                seen += len(data)
                room = max(0, LOG_LIMIT - saved)
                output.write(data[:room])
                saved += min(room, len(data))
                shown.extend(data[:max(0, OUTPUT_LIMIT - len(shown))])
                result[name] = shown.decode('utf-8', errors='replace')
                if seen > OUTPUT_LIMIT:
                    result['truncated'] = True
        if pending:
            result[name] = pending.decode('utf-8', errors='replace')
        else:
            result[name] = shown.decode('utf-8', errors='replace')

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
            list(_files(work))
            await asyncio.sleep(.1)

    try:
        proc = await asyncio.create_subprocess_exec(*command, cwd=work, env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True)
        tasks = [asyncio.create_task(drain(proc.stdout, 'stdout')), asyncio.create_task(drain(proc.stderr, 'stderr')),
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
                await _kill(proc)
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
        result['error'] = str(exc)
    finally:
        if proc:
            await _kill(proc)
            result['exit_code'] = proc.returncode
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
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
    if cancelled:
        raise asyncio.CancelledError
    return result
