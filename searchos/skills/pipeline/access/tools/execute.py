"""执行工具：研究探测、候选 CLI 与正式隔离运行时。"""
from __future__ import annotations

import hashlib
import math
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

ACCESS_TIMEOUT_S = 30


TIMEOUT_SCHEMA = {
    "type": "number", "default": ACCESS_TIMEOUT_S, "minimum": .1,
    "maximum": ACCESS_TIMEOUT_S,
    "description": "执行墙钟秒数，默认30秒；大于30秒的值按30秒执行。",
}


def clamp_access_timeout(value=ACCESS_TIMEOUT_S):
    """Access执行统一限制在0.1到30秒，保留更短预算。"""
    selected = float(ACCESS_TIMEOUT_S if value is None else value)
    if not math.isfinite(selected):
        raise ValueError("timeout must be a finite number")
    return min(ACCESS_TIMEOUT_S, max(.1, selected))


async def execute_command(package_dir, argv, *, work_dir, execution_dir, stdin="",
                          timeout_s=ACCESS_TIMEOUT_S, proxy_mode="inherit",
                          diagnostic_network_override=False, result_store=None, read_only_paths=(),
                          trace_functions=False) -> dict:
    """复用正式执行，完整日志保存为持久脱敏文件。"""
    from searchos.skills.runtime.command_runtime import run_command

    options = {'diagnostic_network_override': True} if diagnostic_network_override else {}
    if trace_functions:
        options['trace_functions'] = True
    if not isinstance(read_only_paths, (tuple, list)):
        raise ValueError('read_only_paths must be a host-provided path sequence')
    allowed_reads = list(read_only_paths)
    if result_store is not None:
        root = Path(result_store.root)
        if root.exists() or root.is_symlink():
            allowed_reads.append(root)
    if allowed_reads:
        options['read_only_paths'] = tuple(allowed_reads)
    result = await run_command(
        package_dir, argv, work_dir=work_dir, execution_dir=execution_dir,
        stdin=stdin, timeout_s=clamp_access_timeout(timeout_s),
        network=True, proxy_mode=proxy_mode, **options,
    )
    execution_id = result.get("execution_id", "")
    if isinstance(execution_id, str) and execution_id and all(
        character.isalnum() or character in "_-" for character in execution_id
    ):
        trace = result.get('function_trace')
        trace_log = Path(execution_dir) / execution_id / 'function-trace.json'
        if result_store is not None and isinstance(trace, dict) and trace_log.is_file() and not trace_log.is_symlink():
            saved_trace = result_store.save_text_file(trace_log)
            result['function_trace'] = {'complete': trace.get('complete', False),
                'call_count': len(trace.get('calls', [])), 'trace_file': saved_trace['path']}
        for stream in ("stdout", "stderr"):
            log = Path(execution_dir) / execution_id / f"{stream}.log"
            if result_store is not None and log.is_file() and not log.is_symlink():
                saved = result_store.save_text_file(log)
                result.setdefault("saved_files", []).append({"field": f"/{stream}", **saved})
                result[f"{stream}_file"] = saved["path"]
                saved_path = Path(saved["path"])
                with saved_path.open(encoding="utf-8") as handle:
                    result[stream] = result_store.read_text_file(
                        handle, path=saved_path, limit=2000
                    )["content"]
                metadata = result.get("streams", {}).get(stream)
                if metadata is not None:
                    metadata["preview_bytes"] = len(result[stream].encode("utf-8"))
                    metadata["preview_truncated"] = metadata.get("total_bytes", saved["total_bytes"]) > metadata["preview_bytes"]
        if streams := result.get("streams"):
            result["truncated"] = any(stream.get("log_truncated") for stream in streams.values())
    return {**result, "work_dir": str(Path(work_dir).resolve())}


_RUNNER = """\
import runpy
import sys
from pathlib import Path
from contextlib import contextmanager

root = Path(__file__).resolve().parent
candidate = root / "candidate"
sys.path.insert(0, str(root / "scripts"))
runpy.run_path(str(root / "scripts" / "check.executed.py"),
              init_globals={"SKILL_DIR": candidate} if candidate.is_dir() else {},
              run_name="__main__")
"""


def _prepare_probe(package: Path, code: str) -> str:
    """原样保存探测代码及执行副本。"""
    (package / "check.py").write_text(code, encoding="utf-8")
    scripts = package / "scripts"
    scripts.mkdir()
    executed = scripts / "check.executed.py"
    executed.write_text(code, encoding="utf-8")
    return code


def _copy_candidate_file(source: Path, target: Path | None = None) -> str:
    """按普通文件读取源版本，同时复制到临时包或计算版本指纹。"""
    from searchos.skills.runtime.command_runtime import _read_only_paths

    source = _read_only_paths((Path(source),))[0]
    directory = os.open(source.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in source.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
    finally:
        os.close(directory)
    digest = hashlib.sha256()
    with os.fdopen(descriptor, 'rb') as handle:
        mode = os.fstat(handle.fileno()).st_mode
        if not stat.S_ISREG(mode):
            raise ValueError('candidate source must be a regular file')
        sink = target.open('wb') if target is not None else None
        try:
            while chunk := handle.read(65536):
                digest.update(chunk)
                if sink is not None:
                    sink.write(chunk)
            if sink is not None:
                os.fchmod(sink.fileno(), stat.S_IMODE(mode))
        finally:
            if sink is not None:
                sink.close()
    return digest.hexdigest()


async def execute_python(code, execute, *, package_parent, candidate_files=None,
                         stdin="", timeout_s=ACCESS_TIMEOUT_S, proxy_mode="inherit") -> dict:
    """在临时只读代码包运行 Python，可提供候选文件快照供验收读取。"""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be nonempty Python text")
    timeout_s = clamp_access_timeout(timeout_s)
    with tempfile.TemporaryDirectory(prefix="access-code-", dir=package_parent) as temporary:
        package = Path(temporary)
        fingerprints = {}
        source_paths = {}
        if candidate_files is not None:
            candidate = package / "candidate"
            candidate.mkdir()
            for relative, source in sorted(candidate_files.items()):
                relative = Path(relative)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("candidate files must use relative package paths")
                target = candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                fingerprints[relative.as_posix()] = _copy_candidate_file(Path(source), target)
                source_paths[relative.as_posix()] = Path(source)
        transformed = _prepare_probe(package, code)
        (package / "runner.py").write_text(_RUNNER, encoding="utf-8")
        result = await execute(
            ["python", "runner.py"], stdin, timeout_s, proxy_mode, package_dir=package
        )
        execution_id = result.get("execution_id", "")
        if isinstance(execution_id, str) and execution_id and all(
            character.isalnum() or character in "_-" for character in execution_id
        ):
            record = Path(package_parent) / "executions" / execution_id
            if record.is_dir() and not record.is_symlink():
                (record / "probe.original.py").write_text(code, encoding="utf-8")
                (record / "probe.executed.py").write_text(transformed, encoding="utf-8")
        changed = []
        for relative, fingerprint in fingerprints.items():
            try:
                current = _copy_candidate_file(source_paths[relative])
            except (OSError, ValueError):
                current = None
            if current != fingerprint:
                changed.append(relative)
        if changed:
            result = {**result, 'status': 'failed',
                      'error': 'candidate_changed_during_execution',
                      'candidate_files_changed': changed}
        return result


PLANNER_EXEC_TOOL = {
    "type": "function",
    "function": {
        "name": "exec",
        "description": (
            "Run Python code to investigate website behavior through HTTP, APIs or "
            "Playwright with explicit headless=True using installed runtime libraries. Print actual response URLs, "
            "status and relevant output supporting the capability plan. Code runs in an "
            "isolated persistent planning work directory; it has no candidate package "
            "or SKILL_DIR. Use relative paths for probe artifacts and sys.executable "
            "for Python subprocesses."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python website investigation code."},
                "timeout_s": dict(TIMEOUT_SCHEMA),
            },
            "required": ["code"],
        },
    },
}


VALIDATOR_EXEC_TOOL = {
    "type": "function",
    "function": {
        "name": "exec",
        "description": (
            "Run a candidate CLI with argv, or run Python verification code with code. "
            "Use exactly one mode. First rerun every pending_regressions command with its original "
            "argv, expected_status and check_kind, then complete normal business calls for each capability. "
            "Keep its entry and capability route; --input business values may vary, such as page=3. "
            "Mark boundary tests with check_kind=boundary. Help, empty, invalid-input and failed calls "
            "cannot support passed. The host attaches actual execution evidence automatically. "
            "Each business call returns validation with JSON, field and source URL checks from this same execution. "
            "Code receives the Python Path variable SKILL_DIR, a read-only candidate snapshot, "
            "and shares the working directory with CLI calls. SKILL_DIR is a Python variable. "
            "Code may read authorized saved-result absolute paths and working-directory files; "
            "read_file supports paging. Compare "
            "results and assert behavior; print the observations supporting your conclusion. "
            "Use sys.executable for Python subprocesses. Candidate CLI calls use package "
            "function defaults and business arguments. Code may use library-native network options for diagnostics."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "capability_id": {
                    "type": "string",
                    "description": "Capability being verified. Required for a candidate CLI argv call.",
                },
                "argv": {"type": "array", "items": {"type": "string"}},
                "check_kind": {
                    "type": "string", "enum": ["positive", "boundary"], "default": "positive",
                    "description": "Mark empty, invalid-input and other boundary probes as boundary.",
                },
                "expected_status": {
                    "type": "string", "enum": ["ok", "empty", "invalid_input"], "default": "ok",
                    "description": "Declare the expected business result before execution; registered boundary examples supply their expectation.",
                },
                "code": {"type": "string", "description": "Python verification code."},
                "stdin": {"type": "string"},
                "timeout_s": dict(TIMEOUT_SCHEMA),
            },
            "oneOf": [{"required": ["argv"]}, {"required": ["code"]}],
        },
    },
}


async def execute_research(workspace, *, code, timeout_s=ACCESS_TIMEOUT_S) -> dict:
    """保存探测的执行来源、退出状态与实际输出。"""
    root = workspace.runtime_dir / "planner"
    root.mkdir(exist_ok=True)

    async def command(argv, stdin, timeout_s, _mode, *, package_dir):
        return await execute_command(
            package_dir, argv, work_dir=root / "work", execution_dir=root / "executions",
            stdin=stdin, timeout_s=timeout_s,
            result_store=workspace.package.result_store,
        )

    result = await execute_python(
        code, command, package_parent=root,
        timeout_s=timeout_s,
    )
    return {**result, "content_source": "execution", "live_evidence": False}


from searchos.skills.pipeline.access.tools.files import _tool

BUILDER_EXEC_TOOL = _tool('exec', '执行候选 CLI 或临时 Python。每次选择 argv 或 code；网络访问由代码配置，完整输出保存文件。', {
    'argv': {'type': 'array', 'items': {'type': 'string'}},
    'code': {'type': 'string'}, 'stdin': {'type': 'string'}, 'timeout_s': dict(TIMEOUT_SCHEMA),
})


class ExecutionTools:
    def __init__(self, package, *, candidate_version):
        self.package = package
        self.candidate_version = candidate_version
        self.work_dir = None

    @contextmanager
    def validation_work(self, number):
        previous = self.work_dir
        self.work_dir = self.package.runtime_dir / f'validation-{number}' / 'work'
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.package.read_roots.add(self.work_dir.resolve())
        try:
            yield self.work_dir
        finally:
            self.work_dir = previous

    async def execute(self, argv=None, stdin='', timeout_s=ACCESS_TIMEOUT_S, *, code=None, package_dir=None,
                   trace_functions=False):
        from searchos.skills.packaging import package_files
        if (argv is None) == (code is None):
            raise ValueError('provide exactly one of argv or code')
        root = self.package.runtime_dir
        work = self.work_dir or root / 'work'
        source = Path(package_dir) if package_dir is not None else self.package.output_dir
        if code is not None:
            fingerprint = self.candidate_version()
            names = list(package_files(source) if package_dir is not None else self.package.files)
            async def command(args, input_text, timeout, _mode, *, package_dir):
                return await execute_command(package_dir, args, work_dir=work,
                    execution_dir=root / 'executions', stdin=input_text, timeout_s=timeout,
                    result_store=self.package.result_store,
                    read_only_paths=tuple(source / name for name in names))
            result = await execute_python(code, command, package_parent=root,
                candidate_files={str(name): source / name for name in names},
                stdin=stdin, timeout_s=timeout_s)
            if fingerprint != self.candidate_version():
                result.update(status='failed', error='candidate_changed_during_execution')
            return result
        return await execute_command(source, argv, work_dir=work, execution_dir=root / 'executions',
            stdin=stdin, timeout_s=timeout_s, result_store=self.package.result_store, trace_functions=trace_functions)
