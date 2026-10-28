"""Access 包结构与真实 CLI 样例校验，不在主进程导入生成代码。"""

from __future__ import annotations

import ast
import io
import json
import os
import re
import stat
import tempfile
import tokenize
from collections.abc import Awaitable, Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from searchos.skills.pipeline.access.tools.execute import ACCESS_TIMEOUT_S

CaseCallback = Callable[[dict], Awaitable[None]]


def _imports_searchos(text: str) -> bool:
    try:
        nodes = ast.walk(ast.parse(text))
        return any(
            name == "searchos" or name.startswith("searchos.")
            for node in nodes
            for name in (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
        )
    except SyntaxError:
        # 一个坏辅助模块不否决其他入口，但它仍不能声明 SearchOS 依赖。
        importing = False
        expect_module = False
        from_import = False
        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                if token.type == tokenize.NEWLINE:
                    importing = expect_module = False
                    from_import = False
                elif token.type == tokenize.NAME and token.string == "from":
                    importing = expect_module = True
                    from_import = True
                elif token.type == tokenize.NAME and token.string == "import":
                    importing = expect_module = not from_import
                elif (
                    importing
                    and not from_import
                    and token.type == tokenize.OP
                    and token.string == ","
                ):
                    expect_module = True
                elif expect_module and token.type == tokenize.NAME:
                    if token.string == "searchos":
                        return True
                    expect_module = False
        except (tokenize.TokenError, IndentationError):
            pass
        return False


def validate_access_structure(
    output_dir: Path,
    expected_name: str,
    *,
    require_host: bool = True,
    expected_host: str | None = None,
) -> dict:
    """只检查可发布包结构，不执行脚本；文档包和局部坏模块可保留。"""
    from searchos.skills.packaging import package_files, validate_package

    try:
        skill = validate_package(output_dir, expected_name=expected_name)
        if skill.meta.category.value != "access":
            raise ValueError(
                "Access packages require metadata.searchos-category: access in SKILL.md frontmatter"
            )
        frontmatter = (output_dir / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
        metadata = (yaml.safe_load(frontmatter) or {}).get("metadata", {})
        if not isinstance(metadata, dict) or metadata.get("searchos-category") != "access":
            raise ValueError(
                "Access packages require metadata.searchos-category: access in SKILL.md frontmatter"
            )
        if not skill.body.strip():
            raise ValueError("Access packages require a nonempty SKILL.md body")
        host = metadata.get("host")
        if require_host and (not isinstance(host, str) or not host.strip()):
            raise ValueError("Access packages require metadata.host in SKILL.md frontmatter")
        if expected_host and str(metadata.get("host", "")).lower() != expected_host.lower():
            raise ValueError(f"generated host does not match the request: expected {expected_host}")
        for relative in package_files(output_dir):
            if relative.suffix == ".py" and _imports_searchos(
                (output_dir / relative).read_text(encoding="utf-8")
            ):
                raise ValueError(f"portable scripts must not import SearchOS: {relative}")
    except (ValueError, OSError, IndexError, yaml.YAMLError) as exc:
        return {
            "valid": False,
            "package_valid": False,
            "stage": "package",
            "error": str(exc),
            "case_results": [],
            "capability_results": {},
        }
    return {
        "valid": True,
        "package_valid": True,
        "stage": "package",
        "case_results": [],
        "capability_results": {},
    }


def package_is_complete(output_dir: Path, expected_name: str) -> bool:
    return validate_access_structure(output_dir, expected_name, require_host=False)["package_valid"]


def _case(example: dict, index: int) -> dict:
    case = {
        "capability_id": example.get("capability_id") or "package",
        "example": index, "status": "incomplete", "valid": False,
        "argv": deepcopy(example.get("argv", [])), "proxy_mode": "inherit",
        "check_kind": example.get("check_kind", "positive"),
        "contract": deepcopy(example),
    }
    if "expected_status" in example:
        case["expected_status"] = example["expected_status"]
    return case


def _example_contract(example: dict) -> None:
    argv = example.get("argv")
    if (not isinstance(argv, list) or len(argv) < 2
            or any(not isinstance(value, str) or '\0' in value for value in argv)):
        raise ValueError("argv must contain an interpreter and a skill script")
    if example.get("proxy_mode", "inherit") != "inherit":
        raise ValueError("validation requires package network defaults; configure network access "
                         "inside package functions and submit business arguments")
    if any(value == "--proxy-mode" or value.startswith("--proxy-mode=") for value in argv):
        raise ValueError("validation accepts business arguments only; bind the route and remove --proxy-mode")
    if example.get("expected_status", "ok") not in ("ok", "empty", "invalid_input"):
        raise ValueError("expected_status must be ok, empty or invalid_input")
    if not isinstance(example.get("output", ""), str):
        raise ValueError("output must be a relative JSON file path or empty")
    if not isinstance(example.get("required_fields", []), list) or any(
            not isinstance(field, str) for field in example.get("required_fields", [])):
        raise ValueError("required_fields must contain field names")


def _documented_entries(output_dir: Path) -> set[str]:
    body = (output_dir / "SKILL.md").read_text(encoding="utf-8")
    metadata = (yaml.safe_load(body.split("---", 2)[1]) or {}).get("metadata", {})
    entries = set(re.findall(
        r"\b(?:python3?|node|bash|sh)\s+[\"\']?(scripts/[\w./-]+\.(?:py|sh|js|mjs|cjs))\b", body))
    entries.update(v.strip() for v in str(metadata.get("searchos-browser-entries", "")).split(",")
                   if v.strip())
    return entries


def _ordinary_positive(example: dict) -> bool:
    return (example.get("expected_status", "ok") == "ok"
            and example.get("check_kind") != "boundary"
            and isinstance(example.get("argv"), list)
            and not any(value in {"--help", "-h", "--version"}
                        for value in example["argv"] if isinstance(value, str)))


def validate_access_preflight(output_dir: Path, expected_name: str, examples: list[dict], *,
                              require_host: bool = True, expected_host: str | None = None) -> dict:
    """静态检查结构和样例登记；业务目标保留未执行状态。"""
    structure = validate_access_structure(output_dir, expected_name, require_host=require_host,
                                          expected_host=expected_host)
    if not structure["package_valid"]:
        return structure
    positives = {example.get("capability_id") or "package" for example in examples
                 if _ordinary_positive(example)}
    cases, capabilities, registered = [], {}, set()
    for index, example in enumerate(examples):
        case = _case(example, index)
        cap = case["capability_id"]
        capabilities.setdefault(cap, {"status": "incomplete", "deterministic": "incomplete",
            "semantic": "incomplete", "reason": "业务 CLI 尚未执行。", "case_indexes": []})
        try:
            _example_contract(example)
            entry = Path(example["argv"][1])
            if (example["argv"][0] not in {"python", "python3", "bash", "sh", "node"}
                    or entry.is_absolute() or ".." in entry.parts or str(entry).startswith('-')):
                raise ValueError("entry must be a relative skill script with a supported interpreter")
            from searchos.skills.runtime.command_runtime import _read_only_paths
            source = _read_only_paths(((Path(output_dir) / entry).absolute(),))[0]
            if not source.is_file() or Path(output_dir).resolve() not in source.parents:
                raise ValueError("entry must be a regular file inside the skill package")
            registered.add(example["argv"][1])
            if cap not in positives:
                raise ValueError("each capability requires an ordinary positive example; "
                                 "boundary cases cannot replace it")
        except (ValueError, TypeError, OSError) as exc:
            case.update(check_kind="contract", error=str(exc))
            cases.append(case)
            capabilities[cap].update(reason=str(exc))
            capabilities[cap]["case_indexes"].append(index)
    missing = sorted(_documented_entries(output_dir) - registered)
    for index, entry in enumerate(missing, len(examples)):
        cases.append({"capability_id": "package", "example": index, "status": "incomplete",
            "valid": False, "argv": [], "entry_path": entry, "check_kind": "contract",
            "error": "register real-data examples for all documented commands"})
    if missing or not capabilities:
        capabilities["package"] = {"status": "incomplete", "deterministic": "incomplete",
            "semantic": "incomplete", "reason": (cases[-1]["error"] if cases else
                "register at least one complete real-data CLI example"),
            "case_indexes": [case["example"] for case in cases if case["capability_id"] == "package"]}
    report = {"valid": False, "package_valid": True, "stage": "preflight", "examples": len(examples),
              "case_results": cases, "capability_results": capabilities}
    if missing:
        report["missing_entries"] = missing
    if cases:
        report["error"] = cases[0]["error"]
    elif not examples:
        report["error"] = "register at least one complete real-data CLI example"
    return report


async def validate_access_package(
    output_dir: Path,
    expected_name: str,
    examples: list[dict],
    *,
    require_host: bool = True,
    expected_host: str | None = None,
    on_case: CaseCallback | None = None,
    registered_examples: list[dict] | None = None,
    artifact_store=None,
) -> dict:
    structure = validate_access_structure(
        output_dir, expected_name, require_host=require_host, expected_host=expected_host
    )
    if not structure["package_valid"]:
        return structure
    documented = _documented_entries(output_dir)
    registered = {
        e["argv"][1]
        for e in (examples if registered_examples is None else registered_examples)
        if len(e.get("argv", [])) >= 2
    }
    report = await validate_examples(output_dir, examples, on_case=on_case, artifact_store=artifact_store)
    missing = sorted(documented - registered)
    if missing:
        cases = report["case_results"]
        for entry in missing:
            case = {
                "capability_id": "package",
                "example": len(cases),
                "status": "incomplete",
                "valid": False,
                "argv": [],
                "entry_path": entry,
                "check_kind": "contract",
                "error": "register real-data examples for all documented commands",
            }
            cases.append(case)
            if on_case is not None:
                await on_case(deepcopy(case))
        report = _summarize_cases(cases)
        report["missing_entries"] = missing
    return report


def _controlled_text(path: Path, roots: list[Path]) -> str:
    """只读取受控根中的普通文件；完整证据同样受日志大小限制。"""
    from searchos.skills.runtime.command_runtime import LOG_LIMIT, _read_only_paths

    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("evidence path must be absolute without parent traversal")
    # 路径校验保留原始组件，阻止 resolve 消除符号链接后扩大读取范围。
    source = _read_only_paths((path,))[0]
    if not any(source == root.resolve() or root.resolve() in source.parents for root in roots):
        raise ValueError("evidence path must remain within the artifact store or execution directory")
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
    with os.fdopen(descriptor, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("evidence must be a regular file")
        if info.st_size > LOG_LIMIT:
            raise ValueError(f"output_limit_exceeded: evidence exceeds {LOG_LIMIT} bytes")
        raw = handle.read(LOG_LIMIT + 1)
        if len(raw) > LOG_LIMIT:
            raise ValueError(f"output_limit_exceeded: evidence exceeds {LOG_LIMIT} bytes")
    return raw.decode('utf-8')


def _captured_stream(result: dict, name: str, *, execution_root: Path | None = None,
                     artifact_store=None) -> str:
    from searchos.skills.runtime.command_runtime import LOG_LIMIT

    streams = result.get("streams") or {}
    if not isinstance(streams, dict) or not isinstance(streams.get(name, {}), dict):
        raise ValueError(f"captured {name} metadata must be an object")
    metadata = streams.get(name, {})
    if metadata.get("log_truncated"):
        raise ValueError(f"output_limit_exceeded: {name} exceeds {LOG_LIMIT} captured bytes")
    roots = ([Path(execution_root)] if execution_root is not None else [])
    if artifact_store is not None:
        roots.append(Path(artifact_store.root))
    execution_id = result.get("execution_id")
    if execution_id is not None and (not isinstance(execution_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", execution_id)):
        raise ValueError("invalid execution id in captured evidence")
    if saved := result.get(f"{name}_file"):
        if not isinstance(saved, str):
            raise ValueError("evidence path must be a file path")
        return _controlled_text(Path(saved), roots)
    if execution_root is not None and execution_id:
        saved = Path(execution_root) / execution_id / f"{name}.log"
        try:
            return _controlled_text(saved, roots)
        except FileNotFoundError:
            pass
    if metadata.get("preview_truncated") or (name == "stdout" and result.get("truncated")):
        raise ValueError(f"complete {name} log unavailable for truncated preview")
    text = result.get(name, "")
    if not isinstance(text, str):
        raise ValueError(f"captured {name} must be text")
    if len(text.encode('utf-8')) > LOG_LIMIT:
        raise ValueError(f"output_limit_exceeded: {name} exceeds {LOG_LIMIT} bytes")
    return text


def _execution_feedback(result: dict, *, execution_root: Path | None = None,
                        artifact_store=None) -> dict:
    feedback = deepcopy(result)
    feedback.update({key: str(result.get(key) or "") for key in ("stdout", "stderr")})
    for name in ("stdout", "stderr"):
        try:
            feedback[name] = _captured_stream(result, name, execution_root=execution_root,
                                               artifact_store=artifact_store)
        except (ValueError, OSError) as exc:
            feedback[f"{name}_capture_error"] = str(exc)
        tail = str(result.get(f"{name}_tail") or result.get(name) or "")[-2000:]
        if tail:
            feedback[f"{name}_tail"] = tail
    return feedback


def _failure_reason(result: dict) -> str:
    """从已捕获的输出构造诊断，不执行生成代码，也不改变成功条件。"""
    details = []
    if error := str(result.get("error") or "").strip():
        details.append(error[:500])
    stdout = str(result.get("stdout") or "").strip()
    try:
        payload = json.loads(stdout)
    except (ValueError, RecursionError):
        payload = None
    structured = []
    if isinstance(payload, dict):
        for key in ("status", "error", "message", "warnings"):
            value = payload.get(key)
            if value:
                if isinstance(value, list):
                    value = value[:3]
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                structured.append(f"{key}={text[:500]}")
    details.extend(structured)
    if stderr := str(result.get("stderr_tail") or result.get("stderr") or "").strip():
        details.append("stderr=" + stderr[-1000:])
    if stdout and not structured:
        tail = str(result.get("stdout_tail") or stdout).strip()
        details.append("stdout=" + tail[-1000:])
    details.append(
        f"exit_code={result.get('exit_code')}; execution_status={result.get('status', 'unknown')}"
    )
    if result.get("timed_out"):
        details.append("timed_out=true")
    return "; ".join(details)[:3500]


def _http_source_url(value) -> bool:
    from urllib.parse import urlparse

    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        return False
    try:
        url = urlparse(value)
        return (
            url.scheme in {"http", "https"}
            and bool(url.hostname)
            and (url.port is None or url.port > 0)
        )
    except ValueError:
        return False


def _summarize_cases(cases: list[dict]) -> dict:
    capabilities = {}
    for case in cases:
        key = case["capability_id"]
        result = capabilities.setdefault(
            key,
            {
                "status": "incomplete",
                "deterministic": "passed",
                "semantic": "incomplete",
                "reason": "",
                "case_indexes": [],
            },
        )
        result["case_indexes"].append(case["example"])
        if case["status"] == "failed" or (
            case["status"] == "incomplete" and result["deterministic"] != "failed"
        ):
            result["deterministic"] = case["status"]
            result["reason"] = case.get("error", "")
    for result in capabilities.values():
        result["status"] = "unavailable" if result["deterministic"] == "failed" else "incomplete"
        if result["deterministic"] == "passed":
            result["reason"] = "固定样例通过；语义验收尚未完成。"
    valid = bool(cases) and all(case["valid"] for case in cases)
    report = {
        "valid": valid,
        "package_valid": True,
        "stage": "complete" if valid else "examples",
        "examples": len(cases),
        "case_results": cases,
        "capability_results": capabilities,
    }
    if not cases:
        report["error"] = "register at least one complete real-data CLI example"
        capabilities["package"] = {
            "status": "incomplete",
            "deterministic": "incomplete",
            "semantic": "incomplete",
            "reason": report["error"],
            "case_indexes": [],
        }
    elif not valid:
        first = next(case for case in cases if not case["valid"])
        # 保留旧的首个错误定位字段；逐项成果由两个 results 字段完整保存。
        report.update(
            {
                k: deepcopy(v)
                for k, v in first.items()
                if k not in {"status", "valid", "payload", "output_text"}
            }
        )
        report["stage"] = first.get("stage", "examples")
    return report


def _failure_status(execution: dict | None, error: str) -> str:
    if execution is not None and (
        execution.get("auth_required")
        or execution.get("timed_out")
        or execution.get("started") is False
        or execution.get("status") in {"blocked", "timed_out"}
    ):
        return "incomplete"
    detail = error + "\n" + str((execution or {}).get("stderr", ""))
    if re.search(
        r"ModuleNotFoundError|No module named|can't open file|"
        r"No such file or directory|FileNotFoundError|complete (?:stdout|stderr) log unavailable",
        detail,
        re.I,
    ):
        return "incomplete"
    return "failed"


def _persist_case(case: dict, artifact_store) -> dict:
    if artifact_store is None:
        return case
    shown = artifact_store.present({
        "valid": bool(case["valid"]), "package_valid": True, "case_results": [case]})
    saved = shown["case_results"][0]
    saved["result_file"] = shown["result_file"]
    saved["saved_files"] = shown.get("saved_files", [])
    return saved


def _record_field_paths(record: dict) -> set[str]:
    """拍平字段路径并保留容器名；对象用点号，数组使用数字下标。"""
    paths = set()
    pending = list(record.items())
    while pending:
        path, value = pending.pop()
        paths.add(path)
        if isinstance(value, dict):
            pending.extend((f"{path}.{key}", child) for key, child in value.items())
        elif isinstance(value, list):
            pending.extend((f"{path}.{index}", child) for index, child in enumerate(value))
    return paths


def validate_execution_result(example: dict, result: dict, *, work_dir: Path,
                              execution_dir: Path | None = None, artifact_store=None,
                              example_index: int = 0) -> dict:
    """检查同一次命令回执和完整产物，不启动或重跑 CLI。"""
    case = _case(example, example_index)
    execution = _execution_feedback(result, execution_root=execution_dir, artifact_store=artifact_store)
    case["execution"] = execution
    if isinstance(result.get('function_trace'), dict):
        case['function_trace'] = deepcopy(result['function_trace'])
    try:
        _example_contract(example)
        expected_status = example.get("expected_status", "ok")
        if result.get("auth_required"):
            case.update(stage="authentication", auth_required=True)
            raise ValueError("authentication required: " + _failure_reason(execution))
        if expected_status == "invalid_input":
            failed = (result.get("exit_code") in (None, 0) or result.get("started") is False
                      or result.get("status", "completed") not in {"completed", "failed"})
        else:
            failed = (result.get("exit_code") != 0 or result.get("started") is False
                      or result.get("status", "completed") != "completed")
        if failed or result.get("error") or result.get("timed_out"):
            raise ValueError("command failed: " + _failure_reason(execution))
        if result.get("truncated"):
            raise ValueError("output_limit_exceeded: complete command output was not captured")
        for name in ("stdout", "stderr"):
            if error := execution.get(f"{name}_capture_error"):
                raise ValueError(error)
        output = example.get("output", "")
        if output:
            if result.get("output_unchanged"):
                raise ValueError("declared output was not updated by this execution")
            relative = Path(output)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("output must remain within the work directory")
            text = _controlled_text(Path(work_dir) / relative, [Path(work_dir)])
            case.update(output=output, output_text=text)
        else:
            text = execution["stdout"]
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"CLI output is not valid JSON (line {exc.lineno}, column {exc.colno}); "
                "keep logs on stderr, select the correct JSON output file, "
                "and check for HTML/login/error responses") from exc
        case["payload"] = data
        if expected_status in {"empty", "invalid_input"}:
            if (not isinstance(data, dict) or data.get("status") != expected_status
                    or data.get("records") != []):
                raise ValueError(f"expected status={expected_status} and records=[]")
        else:
            if (example.get("capability_id") or "expected_status" in example) and (
                    not isinstance(data, dict) or data.get("status") != "ok"):
                raise ValueError("capability success example must return status=ok")
            records = data[example["records_key"]] if example.get("records_key") else data
            if not isinstance(records, list) or not records:
                raise ValueError("example must return a nonempty records array")
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("each record must be an object")
                requires_source = "source_url" in example.get("required_fields", [])
                source = (record.get("source_url") if requires_source
                          else record.get("url") or record.get("source_url"))
                if not _http_source_url(source):
                    raise ValueError("each record must retain a valid HTTP source_url" if requires_source
                                     else "each record must retain a valid HTTP source URL")
                required = example.get("required_fields", [])
                fields = _record_field_paths(record) if required else set()
                missing = [field for field in required if field not in fields]
                if missing:
                    raise ValueError("capability required fields missing: " + ", ".join(missing))
        case.update(status="passed", valid=True)
    except Exception as exc:
        case.update(status=_failure_status(execution, str(exc)), error=str(exc)[:4000])
    return _persist_case(case, artifact_store)


async def validate_examples(
    output_dir: Path, examples: list[dict[str, Any]], *, on_case: CaseCallback | None = None,
    artifact_store=None,
) -> dict:
    """显式逐例执行入口；业务回执复用单次纯检查。"""
    from searchos.skills.runtime.command_runtime import run_command

    positives = {example.get("capability_id") or "package" for example in examples
                 if example.get("expected_status", "ok") == "ok"
                 and example.get("check_kind") != "boundary"}
    cases, entry_checks = [], {}
    for index, example in enumerate(examples):
        case = _case(example, index)
        if case["capability_id"] not in positives:
            case.update(check_kind="contract", error="each capability requires an ordinary positive example; "
                        "boundary cases cannot replace it")
            cases.append(case)
            if on_case is not None:
                await on_case(deepcopy(case))
            continue
        with tempfile.TemporaryDirectory(prefix="searchos-build-validation-") as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            execution = None
            try:
                _example_contract(example)
                entry = tuple(example["argv"][:2])
                if entry not in entry_checks:
                    help_root = root / "help-executions"
                    help_result = await run_command(output_dir, [*entry, "--help"],
                        work_dir=root / "help-work", execution_dir=help_root,
                        timeout_s=15, network=False)
                    entry_checks[entry] = _execution_feedback(help_result, execution_root=help_root,
                                                             artifact_store=artifact_store)
                help_result = entry_checks[entry]
                if (help_result.get("exit_code") != 0 or help_result.get("error")
                        or help_result.get("timed_out") or help_result.get("started") is False):
                    execution = help_result
                    raise ValueError("CLI --help failed: " + _failure_reason(help_result))
                execution = await run_command(output_dir, example["argv"], work_dir=work,
                    execution_dir=root / "executions", timeout_s=ACCESS_TIMEOUT_S,
                    network=True, proxy_mode="inherit")
                captured = execution
                streams = execution.get("streams")
                if (execution.get("truncated") and isinstance(streams, dict) and streams
                        and all(isinstance(stream, dict) and stream.get("log_truncated") is False
                                for stream in streams.values())):
                    # 显式旧入口接收 runtime 的预览标记，完整性由逐流元数据确定。
                    captured = {**execution, "truncated": False}
                case = validate_execution_result(example, captured, work_dir=work,
                    execution_dir=root / "executions", artifact_store=artifact_store, example_index=index)
            except Exception as exc:
                case.update(status=_failure_status(execution, str(exc)), error=str(exc)[:4000])
                if execution is not None:
                    case["execution"] = deepcopy(execution)
                    if execution.get("auth_required"):
                        case.update(stage="authentication", auth_required=True)
                case = _persist_case(case, artifact_store)
            cases.append(case)
            if on_case is not None:
                await on_case(deepcopy(case))
    return _summarize_cases(cases)
