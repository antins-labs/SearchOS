"""Skill Execution 私有 worker；只由 ``executor_runtime`` 启动。"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import io
import json
import os
import socket
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PolicyViolation(PermissionError):
    """Executor 触碰 ExecutionPolicy 禁止的能力。"""


class _CappedText(io.TextIOBase):
    def __init__(self, limit: int) -> None:
        self._limit = max(1, limit)
        self._parts: list[str] = []
        self._size = 0

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        raw = str(text)
        remaining = self._limit - self._size
        if remaining > 0:
            kept = raw[:remaining]
            self._parts.append(kept)
            self._size += len(kept)
        return len(raw)

    def getvalue(self) -> str:
        return "".join(self._parts)


@dataclass
class _SkillContext:
    url: str = ""
    html: str = ""
    markdown: str = ""
    query: str = ""
    skill_dir: Path | None = None
    browser: Any = None
    judge_model: Any = None
    extras: dict[str, Any] = field(default_factory=dict)


def _inside(path: Path, roots: tuple[Path, ...]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _resolved_path(value: Any) -> Path | None:
    if isinstance(value, int) or value is None:
        return None
    try:
        raw = os.fsdecode(value)
    except TypeError:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve(strict=False)


def _is_write_open(args: tuple[Any, ...]) -> bool:
    mode = args[1] if len(args) > 1 else "r"
    flags = args[2] if len(args) > 2 else 0
    if isinstance(mode, str) and any(char in mode for char in "wax+"):
        return True
    if isinstance(flags, int):
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        return bool(flags & write_flags)
    return False


def _python_read_roots(skill_dir: Path, sandbox_dir: Path) -> tuple[Path, ...]:
    roots = {skill_dir, sandbox_dir, Path(sys.prefix), Path(sys.base_prefix)}
    for item in sys.path:
        if not item:
            continue
        path = Path(item).resolve(strict=False)
        if path.name in {"site-packages", "dist-packages"}:
            roots.add(path)
        elif (path / "searchos").is_dir():
            # Editable installs add the repository root. Only the package tree
            # is required; allowing the whole repository would expose .env.
            roots.add(path / "searchos")
    for system_root in (
        "/System",
        "/usr/lib",
        "/Library/Frameworks",
        # Python's mimetypes module consults this read-only system table on
        # macOS.  It contains no user secrets and is needed by openpyxl.
        "/private/etc/apache2",
        "/etc/apache2",
        "/private/etc/ssl",
        "/etc/ssl",
        "/dev",
    ):
        path = Path(system_root)
        if path.exists():
            roots.add(path)
    return tuple(path.resolve(strict=False) for path in roots)


def _resolved_allowed_network_hosts(policy: dict[str, Any]) -> tuple[set[str], set[str]]:
    hosts = {str(host).lower().rstrip(".") for host in policy.get("allowed_hosts", [])}
    addresses: set[str] = set()
    for host in hosts:
        try:
            for info in socket.getaddrinfo(host, None):
                addresses.add(str(info[4][0]).lower().rstrip("."))
        except OSError:
            continue
    return hosts, addresses


def _is_playwright_driver(args: tuple[Any, ...]) -> bool:
    """Recognize Playwright's fixed Node driver command, not arbitrary Node."""
    if len(args) < 2:
        return False
    executable = _resolved_path(args[0])
    command = args[1]
    if executable is None or not isinstance(command, (list, tuple)):
        return False
    parts = executable.parts
    try:
        driver_index = parts.index("playwright") + 1
    except ValueError:
        return False
    if parts[driver_index : driver_index + 1] != ("driver",):
        return False
    if executable.name not in {"node", "node.exe"}:
        return False
    argv = [os.fsdecode(item) for item in command]
    return (
        len(argv) == 3
        and _resolved_path(argv[0]) == executable
        and Path(argv[1]).name == "cli.js"
        and "playwright" in Path(argv[1]).parts
        and argv[2] == "run-driver"
    )


def _install_policy(
    policy: dict[str, Any],
    *,
    skill_dir: Path,
    sandbox_dir: Path,
) -> None:
    read_roots = _python_read_roots(skill_dir, sandbox_dir)
    write_roots = [sandbox_dir]
    if policy.get("allow_skill_write"):
        write_roots.append(skill_dir)
    write_roots_tuple = tuple(write_roots)
    network_mode = str(policy.get("network_access", "none"))
    allowed_hosts, allowed_addresses = _resolved_allowed_network_hosts(policy)
    allow_native = bool(policy.get("allow_native_escape_modules", False))
    allow_browser = bool(policy.get("allow_browser_automation", False))

    def require_read(value: Any) -> None:
        path = _resolved_path(value)
        if path is not None and not _inside(path, read_roots):
            raise PolicyViolation(f"file read denied: {path}")

    def require_write(value: Any) -> None:
        path = _resolved_path(value)
        if path is not None and not _inside(path, write_roots_tuple):
            raise PolicyViolation(f"file write denied: {path}")

    def require_network(host: Any) -> None:
        if network_mode == "any":
            return
        normalized = str(host or "").lower().rstrip(".")
        if network_mode == "target_hosts" and (
            normalized in allowed_hosts or normalized in allowed_addresses
        ):
            return
        raise PolicyViolation(f"network access denied: {normalized or '<unknown>'}")

    mutating_path_events = {
        "os.remove": (0,),
        "os.rmdir": (0,),
        "os.mkdir": (0,),
        "os.truncate": (0,),
        "os.chmod": (0,),
        "os.chown": (0,),
        "os.link": (0, 1),
        "os.symlink": (0, 1),
        "os.rename": (0, 1),
        "os.replace": (0, 1),
    }

    def audit(event: str, args: tuple[Any, ...]) -> None:
        if event == "open":
            (require_write if _is_write_open(args) else require_read)(args[0])
            return
        if event in mutating_path_events:
            for index in mutating_path_events[event]:
                if index < len(args):
                    require_write(args[index])
            return
        if event in {"os.listdir", "os.scandir", "os.chdir"} and args:
            require_read(args[0])
            return
        if event in {
            "subprocess.Popen",
            "os.system",
            "os.posix_spawn",
            "os.posix_spawnp",
            "pty.spawn",
        }:
            if event == "subprocess.Popen" and allow_browser and _is_playwright_driver(args):
                return
            raise PolicyViolation(f"subprocess access denied: {event}")
        if event in {"socket.getaddrinfo", "socket.gethostbyname"} and args:
            require_network(args[0])
            return
        if event in {"socket.connect", "socket.sendto", "socket.bind"} and len(args) > 1:
            address = args[1]
            host = address[0] if isinstance(address, tuple) and address else address
            require_network(host)
            return
        if event == "import" and args and not allow_native:
            root = str(args[0]).partition(".")[0]
            if root in {"ctypes", "_ctypes", "cffi", "_cffi_backend"}:
                # ImportError lets optional dependencies degrade normally while
                # keeping the native escape hatch unavailable to executor code.
                raise ImportError(f"native escape module denied: {root}")

    sys.addaudithook(audit)


def _apply_resource_limits(policy: dict[str, Any]) -> None:
    try:
        import resource
    except ImportError:
        return

    limits = (
        ("RLIMIT_CPU", int(policy.get("cpu_time_s", 65))),
        ("RLIMIT_AS", int(policy.get("memory_bytes", 1_500_000_000))),
        ("RLIMIT_FSIZE", int(policy.get("max_result_bytes", 2_000_000) * 2)),
        ("RLIMIT_NOFILE", int(policy.get("max_open_files", 128))),
    )
    for name, value in limits:
        kind = getattr(resource, name, None)
        if kind is None or value <= 0:
            continue
        try:
            current_soft, current_hard = resource.getrlimit(kind)
            ceiling = value if current_hard < 0 else min(value, current_hard)
            resource.setrlimit(kind, (ceiling, ceiling))
        except (OSError, ValueError):
            continue


def _validate_result(result: Any, policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return _error("invalid_result", "executor result must be a dict")
    try:
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        return _error("invalid_result", f"executor result is not valid JSON: {exc}")
    maximum = int(policy.get("max_result_bytes", 2_000_000))
    if len(encoded) > maximum:
        return _error(
            "invalid_result",
            f"executor result exceeds {maximum} bytes ({len(encoded)} bytes)",
        )
    return result


async def _call_executor(request: dict[str, Any]) -> dict[str, Any]:
    executor_path = Path(request["executor_path"])
    skill_dir = Path(request["skill_dir"])
    sys.path.insert(0, str(skill_dir))
    # Proxy defaults are process-local now; installing them here cannot mutate
    # the SearchOS host process. Generated policies receive no proxy secrets.
    try:
        from searchos.skills.runtime.executor_proxy import install_executor_proxy_shims

        install_executor_proxy_shims()
    except PolicyViolation:
        raise
    except Exception:
        pass
    spec = importlib.util.spec_from_file_location(
        f"searchos_skill_{os.getpid()}",
        str(executor_path),
    )
    if spec is None or spec.loader is None:
        return _error("executor_error", f"cannot load executor: {executor_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    execute = getattr(module, "execute", None)
    if execute is None or not callable(execute):
        return _error("executor_error", "executor.py has no callable execute()")

    context = _SkillContext(
        query=str(request.get("query", "")),
        skill_dir=skill_dir,
    )
    result = execute(dict(request.get("params", {})), context)
    if inspect.isawaitable(result):
        result = await result
    return _validate_result(result, request["policy"])


def _run_probe(request: dict[str, Any], stdout: _CappedText, stderr: _CappedText) -> dict[str, Any]:
    namespace = {
        "__name__": "__main__",
        "__file__": str(Path(request["working_dir"]) / "<skill-probe>"),
    }
    try:
        exec(compile(str(request.get("code", "")), namespace["__file__"], "exec"), namespace)
        return {"exit_code": 0, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}
    except PolicyViolation:
        raise
    except BaseException:  # noqa: BLE001
        traceback.print_exc(file=stderr)
        return {"exit_code": 1, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}


def _error(error_type: str, message: str) -> dict[str, Any]:
    return {"error": str(message), "error_type": error_type}


def main() -> int:
    try:
        request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        policy = dict(request["policy"])
        sandbox_dir = Path(request["sandbox_dir"]).resolve()
        skill_dir = Path(
            request.get("skill_dir") or request.get("working_dir") or sandbox_dir
        ).resolve()
        _apply_resource_limits(policy)
        _install_policy(policy, skill_dir=skill_dir, sandbox_dir=sandbox_dir)

        limit = int(policy.get("max_output_bytes", 16_000))
        captured_stdout = _CappedText(limit)
        captured_stderr = _CappedText(limit)
        with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
            if request.get("mode") == "executor":
                result = asyncio.run(_call_executor(request))
            elif request.get("mode") == "probe":
                result = _run_probe(request, captured_stdout, captured_stderr)
            else:
                result = _error("invalid_request", "unknown worker mode")
    except PolicyViolation as exc:
        result = _error("policy_violation", str(exc))
    except BaseException as exc:  # noqa: BLE001
        result = _error("executor_error", f"{type(exc).__name__}: {exc}")

    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
