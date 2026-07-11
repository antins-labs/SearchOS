"""受策略约束的 Skill Execution 模块。

``executor.py`` 永远不会在 SearchOS 主进程中导入。调用会被序列化到独立
Python worker；该 worker 使用最小环境变量、文件访问策略、网络策略、资源上限、
进程组超时和结构化结果校验。``run_executor`` 保留原调用形状，作为现有 typed
tool 的稳定接口。

Python audit hook 不是完整的操作系统虚拟机，但与独立进程、环境清理和资源限制
组合后，可以阻止普通 Python executor 读取用户文件、启动命令或污染主进程。
动态生成的 Skill 额外禁用 native escape 模块，并只允许访问目标主机。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import tempfile
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger(__name__)

EXECUTOR_TIMEOUT = 60.0
_WORKER = Path(__file__).with_name("_executor_worker.py")
_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


class NetworkAccess(StrEnum):
    """Worker 可使用的网络范围。"""

    NONE = "none"
    TARGET_HOSTS = "target_hosts"
    ANY = "any"


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """一次 Skill Execution 的全部权限和资源不变量。"""

    timeout_s: float = EXECUTOR_TIMEOUT
    network_access: NetworkAccess = NetworkAccess.NONE
    allowed_hosts: tuple[str, ...] = ()
    allow_skill_write: bool = False
    inherit_proxy: bool = False
    allow_native_escape_modules: bool = False
    allow_browser_automation: bool = False
    max_result_bytes: int = 2_000_000
    max_output_bytes: int = 16_000
    cpu_time_s: int = 65
    memory_bytes: int = 1_500_000_000
    max_open_files: int = 128

    def __post_init__(self) -> None:
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if self.max_result_bytes <= 0 or self.max_output_bytes <= 0:
            raise ValueError("result/output limits must be positive")
        if self.network_access is NetworkAccess.TARGET_HOSTS and not self.allowed_hosts:
            raise ValueError("target-host network policy requires allowed_hosts")

    @classmethod
    def bundled(cls, **overrides: Any) -> ExecutionPolicy:
        """已审入仓库的 Skill：允许联网和固定浏览器 driver，禁止任意子进程。"""
        policy = cls(
            network_access=NetworkAccess.ANY,
            inherit_proxy=True,
            allow_native_escape_modules=False,
            # Bundled skills are repository-reviewed and some still require
            # Playwright. The worker permits only Playwright's fixed driver
            # command, never a general executable.
            allow_browser_automation=True,
        )
        return replace(policy, **overrides)

    @classmethod
    def generated(
        cls,
        allowed_hosts: tuple[str, ...] | list[str],
        **overrides: Any,
    ) -> ExecutionPolicy:
        """LLM 生成的 Skill：仅可访问生成任务明确给出的目标主机。"""
        hosts = tuple(sorted({host.strip().lower() for host in allowed_hosts if host.strip()}))
        policy = cls(
            network_access=(NetworkAccess.TARGET_HOSTS if hosts else NetworkAccess.NONE),
            allowed_hosts=hosts,
            inherit_proxy=False,
            allow_native_escape_modules=False,
        )
        return replace(policy, **overrides)

    def to_wire(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["network_access"] = self.network_access.value
        return payload


async def run_executor(
    skill_path: Path,
    params: dict[str, Any],
    browser_tools: dict[str, Any] | None = None,
    *,
    query: str = "",
    judge_model: Any = None,
    policy: ExecutionPolicy | None = None,
) -> dict[str, Any]:
    """在隔离 worker 中执行 ``executor.py`` 并返回经过校验的字典。

    ``browser_tools`` 和 ``judge_model`` 仅为旧调用兼容而保留。可调用对象和模型
    绝不会跨越执行 seam，避免把主进程对象或密钥暴露给 executor。现有打包
    Access Skill 均使用直接 HTTP/浏览器实现，不依赖这两个字段。
    """
    del browser_tools, judge_model
    selected = policy or ExecutionPolicy.bundled()
    skill_dir = Path(skill_path).resolve()
    executor_path = (skill_dir / "executor.py").resolve()

    try:
        executor_path.relative_to(skill_dir)
    except ValueError:
        return _error("policy_violation", "executor.py escapes the skill directory")
    if not executor_path.is_file():
        return _error("missing_executor", f"No executor.py in {skill_dir}")
    if not isinstance(params, dict):
        return _error("invalid_request", "executor params must be a dict")
    try:
        json.dumps(params, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        return _error("invalid_request", f"executor params are not JSON-serializable: {exc}")

    request = {
        "mode": "executor",
        "skill_dir": str(skill_dir),
        "executor_path": str(executor_path),
        "params": params,
        "query": str(query or ""),
        "policy": selected.to_wire(),
    }
    result = await _run_worker(request, selected, cwd=skill_dir)
    if result.get("error"):
        logger.warning(
            "Executor %s failed (%s): %s",
            skill_dir.name,
            result.get("error_type", "executor_error"),
            result.get("error"),
        )
    else:
        logger.info("Executor %s completed", skill_dir.name)
    return result


async def run_python_probe(
    code: str,
    working_dir: Path,
    *,
    policy: ExecutionPolicy,
) -> dict[str, Any]:
    """在同一执行 seam 中运行动态构建器探针代码。"""
    workspace = Path(working_dir).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    probe_policy = replace(policy, allow_skill_write=True)
    request = {
        "mode": "probe",
        "working_dir": str(workspace),
        "code": str(code),
        "policy": probe_policy.to_wire(),
    }
    result = await _run_worker(request, probe_policy, cwd=workspace)
    if "exit_code" in result:
        return result
    return {
        "exit_code": -1,
        "stdout": "",
        "stderr": f"{result.get('error_type', 'worker_error')}: {result.get('error', '')}",
    }


async def _run_worker(
    request: dict[str, Any],
    policy: ExecutionPolicy,
    *,
    cwd: Path,
) -> dict[str, Any]:
    if not _WORKER.is_file():
        return _error("worker_error", f"Skill worker is missing: {_WORKER}")

    with tempfile.TemporaryDirectory(prefix="searchos-skill-") as sandbox_dir:
        request["sandbox_dir"] = sandbox_dir
        env = _worker_environment(policy, Path(sandbox_dir))
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                str(_WORKER),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
                env=env,
                start_new_session=(os.name == "posix"),
            )
        except Exception as exc:  # noqa: BLE001
            return _error("worker_error", f"cannot start isolated worker: {exc}")

        wire = json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8")
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(wire),
                timeout=policy.timeout_s,
            )
        except TimeoutError:
            await _kill_process_group(proc)
            return _error("timeout", f"Executor timed out after {policy.timeout_s:g}s")

        if proc.returncode != 0 and not stdout:
            detail = stderr.decode("utf-8", errors="replace")[-4000:]
            return _error(
                "resource_limit" if proc.returncode and proc.returncode < 0 else "worker_error",
                f"isolated worker exited with code {proc.returncode}: {detail}",
            )
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            detail = stderr.decode("utf-8", errors="replace")[-2000:]
            return _error("worker_error", f"invalid worker response: {exc}; {detail}")
        if not isinstance(payload, dict):
            return _error("worker_error", "worker response must be a dict")
        return payload


async def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except ProcessLookupError:
        pass
    try:
        await proc.wait()
    except Exception:  # noqa: BLE001
        pass


def _worker_environment(policy: ExecutionPolicy, sandbox_dir: Path) -> dict[str, str]:
    env = {
        "HOME": str(sandbox_dir),
        "TMPDIR": str(sandbox_dir),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for key in ("LANG", "LC_ALL", "TZ", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        if value := os.environ.get(key):
            env[key] = value
    if policy.inherit_proxy:
        for key in _PROXY_ENV_KEYS:
            if value := os.environ.get(key):
                env[key] = _sanitized_proxy_value(key, value)
    if policy.allow_browser_automation:
        if browser_path := _playwright_browsers_path():
            # Keep HOME isolated while letting reviewed Bundled Skills locate
            # the separately installed browser runtime.
            env["PLAYWRIGHT_BROWSERS_PATH"] = browser_path
    return env


def _playwright_browsers_path() -> str:
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured:
        return configured
    candidates = [
        Path.home() / "Library/Caches/ms-playwright",
        Path.home() / ".cache/ms-playwright",
    ]
    if local_app_data := os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(local_app_data) / "ms-playwright")
    return next((str(path) for path in candidates if path.is_dir()), "")


def _sanitized_proxy_value(key: str, value: str) -> str:
    if key.lower() == "no_proxy":
        return value
    try:
        parsed = urlsplit(value)
        if not parsed.hostname:
            return value.rsplit("@", 1)[-1]
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = f"{host}:{parsed.port}" if parsed.port else host
        return urlunsplit((parsed.scheme, netloc, "", "", ""))
    except (TypeError, ValueError):
        return ""


def _error(error_type: str, message: str) -> dict[str, Any]:
    return {"error": message, "error_type": error_type}


__all__ = [
    "EXECUTOR_TIMEOUT",
    "ExecutionPolicy",
    "NetworkAccess",
    "run_executor",
    "run_python_probe",
]
