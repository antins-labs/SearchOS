"""执行工具：研究探测、候选 CLI 与正式隔离运行时。"""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

ACCESS_TIMEOUT_S = 60
MAX_ACCESS_TIMEOUT_S = 300


TIMEOUT_SCHEMA = {
    "type": "number", "default": ACCESS_TIMEOUT_S, "minimum": .1,
    "maximum": MAX_ACCESS_TIMEOUT_S,
    "description": "执行墙钟秒数，默认60秒，最大300秒。",
}


def clamp_access_timeout(value=ACCESS_TIMEOUT_S):
    """执行预算默认60秒，调用方可选择0.1到300秒。"""
    selected = float(ACCESS_TIMEOUT_S if value is None else value)
    if not math.isfinite(selected):
        raise ValueError("timeout must be a finite number")
    return min(MAX_ACCESS_TIMEOUT_S, max(.1, selected))


async def execute_command(package_dir, argv, *, work_dir, execution_dir, stdin="",
                          timeout_s=ACCESS_TIMEOUT_S, result_store=None, read_only_paths=(),
                          trace_functions=False, browser=False, browser_request=None) -> dict:
    """复用正式执行，完整日志保存为持久脱敏文件。"""
    from searchos.skills.runtime.command_runtime import run_command

    options = {}
    if browser:
        options['browser'] = True
    if browser_request is not None:
        options['browser_request'] = browser_request
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
        network=True, **options,
    )
    if not result.get('execution_id') and result.get('started') is False:
        result['execution_id'] = 'attempt-' + uuid4().hex
        record = Path(execution_dir) / result['execution_id']
        record.mkdir(parents=True)
        (record / 'record.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    execution_id = result.get("execution_id", "")
    if isinstance(execution_id, str) and execution_id and all(
        character.isalnum() or character in "_-" for character in execution_id
    ):
        if result_store is not None:
            result['artifact_files'] = {}
            for artifact in result.get('artifacts', []):
                relative = Path(artifact['path'])
                if (relative.is_absolute() or '..' in relative.parts
                        or relative.as_posix() not in result.get('updated_files', [])):
                    continue
                source = Path(execution_dir) / execution_id / 'artifacts' / relative
                if source.is_file() and not source.is_symlink():
                    result['artifact_files'][relative.as_posix()] = result_store.save_text_file(source)['path']
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
import os
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
candidate = root / "candidate"
if candidate.is_dir():
    os.environ['SKILL_DIR'] = str(candidate)
    os.environ['PYTHONPATH'] = str(candidate)
    sys.path.insert(0, str(candidate))
runpy.run_path(str(root / "probe.py"),
              init_globals={"SKILL_DIR": candidate} if candidate.is_dir() else {},
              run_name="__main__")
"""


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
                         stdin="", timeout_s=ACCESS_TIMEOUT_S) -> dict:
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
        (package / "probe.py").write_text(code, encoding="utf-8")
        (package / "runner.py").write_text(_RUNNER, encoding="utf-8")
        result = await execute(
            ["python", "runner.py"], stdin, timeout_s, package_dir=package
        )
        execution_id = result.get("execution_id", "")
        if isinstance(execution_id, str) and execution_id and all(
            character.isalnum() or character in "_-" for character in execution_id
        ):
            record = Path(package_parent) / "executions" / execution_id
            if record.is_dir() and not record.is_symlink():
                (record / "probe.py").write_text(code, encoding="utf-8")
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


EXEC_TOOL = {
    "type": "function",
    "function": {
        "name": "exec",
        "description": (
            "在独立进程中执行一条命令或一段 Python，工作目录跨调用保留。每次提供 argv 或 code 其中一项。"
            "开发和验收角色可通过 SKILL_DIR 访问候选包，Planner 使用探测工作目录。"
            "返回 execution_id、退出状态、输出和产物。按返回路径读取完整日志，在验收报告中提交执行归属、输出位置与回归关系。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "argv": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                         "description": "按顺序传入命令及各个参数，支持解释器选项和模块运行。"},
                "code": {"type": "string", "description": "原样执行的 Python 代码。"},
                "stdin": {"type": "string", "default": "", "description": "写入进程标准输入的文本。"},
                "browser": {"type": "boolean", "default": False, "description": "需要连接 SearchOS 管理的站点浏览器时设为 true。"},
                "timeout_s": dict(TIMEOUT_SCHEMA),
            },
            "oneOf": [{"required": ["argv"]}, {"required": ["code"]}],
            "additionalProperties": False,
        },
    },
}


PLANNER_EXEC_TOOL = BUILDER_EXEC_TOOL = VALIDATOR_EXEC_TOOL = EXEC_TOOL


async def execute_research(workspace, *, argv=None, code=None, stdin='', timeout_s=ACCESS_TIMEOUT_S, browser=False) -> dict:
    """保存探测的执行来源、退出状态与实际输出。"""
    root = workspace.runtime_dir / "planner"
    root.mkdir(exist_ok=True)
    if (argv is None) == (code is None):
        raise ValueError('provide exactly one of argv or code')
    request = {'role': 'planner', 'browser': browser, 'timeout_s': timeout_s, 'stdin': stdin,
               **({'code': code} if code is not None else {'argv': argv})}

    async def command(argv, stdin, timeout_s, *, package_dir):
        return await execute_command(
            package_dir, argv, work_dir=root / "work", execution_dir=root / "executions",
            stdin=stdin, timeout_s=timeout_s,
            result_store=workspace.package.result_store,
            browser=browser, browser_request=request,
        )

    if argv is not None:
        package = root / 'probe'
        package.mkdir(exist_ok=True)
        result = await command(argv, stdin, timeout_s, package_dir=package)
    else:
        result = await execute_python(
            code, command, package_parent=root,
            stdin=stdin, timeout_s=timeout_s)
    return {**result, "content_source": "execution", "live_evidence": False}


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
                   trace_functions=False, browser=False, browser_request=None):
        from searchos.skills.packaging import package_files
        if (argv is None) == (code is None):
            raise ValueError('provide exactly one of argv or code')
        root = self.package.runtime_dir
        work = self.work_dir or root / 'work'
        source = Path(package_dir) if package_dir is not None else self.package.output_dir
        if code is not None:
            fingerprint = self.candidate_version()
            names = list(package_files(source) if package_dir is not None else self.package.files)
            async def command(args, input_text, timeout, *, package_dir):
                return await execute_command(package_dir, args, work_dir=work,
                    execution_dir=root / 'executions', stdin=input_text, timeout_s=timeout,
                    result_store=self.package.result_store,
                    browser=browser, browser_request=browser_request or {'code': code, 'stdin': stdin, 'browser': browser, 'timeout_s': timeout_s},
                    read_only_paths=tuple(source / name for name in names))
            result = await execute_python(code, command, package_parent=root,
                candidate_files={str(name): source / name for name in names},
                stdin=stdin, timeout_s=timeout_s)
            if fingerprint != self.candidate_version():
                result.update(status='failed', error='candidate_changed_during_execution')
            return result
        return await execute_command(source, argv, work_dir=work, execution_dir=root / 'executions',
            stdin=stdin, timeout_s=timeout_s, result_store=self.package.result_store, trace_functions=trace_functions,
            browser=browser, browser_request=browser_request or {'argv': argv, 'stdin': stdin,
                'timeout_s': timeout_s, 'browser': browser})
