"""Access 包结构与真实 CLI 样例校验，不在主进程导入生成代码。"""
from __future__ import annotations
import ast
import json
import yaml
import logging
import tempfile
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

def package_is_complete(output_dir: Path, expected_name: str) -> bool:
    from searchos.skills.packaging import validate_package

    try:
        validate_package(output_dir, expected_name=expected_name)
        scripts = [p for p in (output_dir / "scripts").rglob("*") if p.is_file()]
        if not any(p.suffix in {".py", ".sh", ".js", ".mjs", ".cjs"} for p in scripts):
            return False
        for script in scripts:
            if script.suffix == ".py":
                for node in ast.walk(ast.parse(script.read_text(encoding="utf-8"))):
                    names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else (
                        [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                    if any(name == "searchos" or name.startswith("searchos.") for name in names):
                        return False
        return True
    except (ValueError, OSError, SyntaxError, yaml.YAMLError):
        logger.warning("invalid portable package: %s", output_dir, exc_info=True)
        return False


async def validate_access_package(output_dir: Path, expected_name: str, examples: list[dict], *,
                                  require_host: bool = True, expected_host: str | None = None) -> dict:
    from searchos.skills.packaging import validate_package
    try:
        skill = validate_package(output_dir, expected_name=expected_name)
        if skill.meta.category.value != "access":
            raise ValueError("Access packages require metadata.searchos-category: access in SKILL.md frontmatter")
        frontmatter = (output_dir / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
        metadata = (yaml.safe_load(frontmatter) or {}).get("metadata", {})
        if not isinstance(metadata, dict) or metadata.get('searchos-category') != 'access':
            raise ValueError("Access packages require metadata.searchos-category: access in SKILL.md frontmatter")
        if not skill.body.strip():
            raise ValueError("Access packages require a nonempty SKILL.md body")
        if require_host and not str(metadata.get("host", "")).strip():
            raise ValueError("Access packages require metadata.host in SKILL.md frontmatter")
        if expected_host and str(metadata.get('host', '')).lower() != expected_host.lower():
            raise ValueError(f"generated host does not match the request: expected {expected_host}")
        if not package_is_complete(output_dir, expected_name):
            raise ValueError("require SKILL.md and valid CLI scripts without SearchOS imports")
        body = (output_dir / 'SKILL.md').read_text(encoding='utf-8')
        documented = set(re.findall(r'\b(?:python3?|node|bash|sh)\s+[\"\']?(scripts/[\w./-]+\.(?:py|sh|js|mjs|cjs))\b', body))
        documented.update(v.strip() for v in str(metadata.get('searchos-browser-entries', '')).split(',') if v.strip())
        registered = {e['argv'][1] for e in examples if len(e.get('argv', [])) >= 2}
        if missing := documented - registered:
            return {'valid': False, 'stage': 'examples', 'error': 'register real-data examples for all documented commands',
                    'missing_entries': sorted(missing)}
    except (ValueError, OSError, yaml.YAMLError) as exc:
        return {"valid": False, "stage": "package", "error": str(exc)}
    return await validate_examples(output_dir, examples)


def _execution_feedback(result: dict) -> dict:
    feedback = {key: result[key] for key in
                ('exit_code', 'status', 'timed_out', 'started') if key in result}
    feedback.update({key: str(result.get(key) or '')[:2000] for key in ('stdout', 'stderr')})
    return feedback


def _failure_reason(result: dict) -> str:
    """从已捕获的输出构造诊断，不执行生成代码，也不改变成功条件。"""
    details = []
    if error := str(result.get('error') or '').strip():
        details.append(error[:500])
    stdout = str(result.get('stdout') or '').strip()
    try:
        payload = json.loads(stdout)
    except (ValueError, RecursionError):
        payload = None
    structured = []
    if isinstance(payload, dict):
        for key in ('status', 'error', 'message', 'warnings'):
            value = payload.get(key)
            if value:
                if isinstance(value, list):
                    value = value[:3]
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                structured.append(f'{key}={text[:500]}')
    details.extend(structured)
    if stderr := str(result.get('stderr') or '').strip():
        details.append('stderr=' + stderr[:1000])
    if stdout and not structured:
        details.append('stdout=' + stdout[:1000])
    details.append(f"exit_code={result.get('exit_code')}; execution_status={result.get('status', 'unknown')}")
    if result.get('timed_out'):
        details.append('timed_out=true')
    return '; '.join(details)[:3500]


def _http_source_url(value) -> bool:
    from urllib.parse import urlparse
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        return False
    try:
        url = urlparse(value)
        return url.scheme in {'http', 'https'} and bool(url.hostname) and (url.port is None or url.port > 0)
    except ValueError:
        return False


async def validate_examples(output_dir: Path, examples: list[dict[str, Any]]) -> dict:
    from searchos.skills.runtime.command_runtime import run_command
    if not examples:
        return {"valid": False, "stage": "examples", "error": "register at least one complete real-data CLI example"}
    positives = [example for example in examples if example.get('expected_status', 'ok') == 'ok'
                 and example.get('check_kind') != 'boundary']
    positive_capabilities = {example.get('capability_id') for example in positives}
    for index, example in enumerate(examples):
        capability = example.get('capability_id')
        if not positives or (capability and capability not in positive_capabilities):
            report = {'valid': False, 'stage': 'examples', 'example': index, 'check_kind': 'contract',
                      'error': 'each capability requires an ordinary positive example; boundary cases cannot replace it'}
            if capability:
                report['capability_id'] = capability
            return report
    checked_entries = set()
    for index, example in enumerate(examples):
        with tempfile.TemporaryDirectory(prefix="searchos-build-validation-") as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            execution = None
            try:
                expected_status = example.get('expected_status', 'ok')
                if expected_status not in ('ok', 'empty', 'invalid_input'):
                    raise ValueError('expected_status must be ok, empty or invalid_input')
                entry = tuple(example["argv"][:2])
                if entry not in checked_entries:
                    help_result = await run_command(output_dir, [*entry, "--help"], work_dir=root / "help-work",
                        execution_dir=root / "help-executions", timeout_s=15, network=False)
                    execution = help_result
                    if help_result.get("exit_code") != 0 or help_result.get("error"):
                        raise ValueError("CLI --help failed: " + _failure_reason(help_result))
                    checked_entries.add(entry)
                result = await run_command(output_dir, example["argv"], work_dir=work,
                    execution_dir=root / "executions", timeout_s=60, network=True,
                    proxy_mode=example.get('proxy_mode', 'inherit'))
                execution = result
                if result.get('auth_required'):
                    return {'valid': False, 'stage': 'authentication', 'auth_required': True,
                            'example': index, 'argv': example['argv'], 'proxy_mode': example.get('proxy_mode', 'inherit'),
                            'error': 'authentication required: ' + _failure_reason(result),
                            'execution': _execution_feedback(result)}
                if expected_status == 'invalid_input':
                    execution_failed = (result.get('exit_code') in (None, 0) or result.get('started') is False
                                        or result.get('status', 'completed') not in {'completed', 'failed'})
                else:
                    execution_failed = result.get('exit_code') != 0 or result.get('status', 'completed') != 'completed'
                if execution_failed or result.get('error') or result.get('timed_out'):
                    raise ValueError('command failed: ' + _failure_reason(result))
                output = example.get("output", "")
                if output:
                    artifact = (work / output).resolve()
                    artifact.relative_to(work.resolve())
                    if artifact.is_symlink() or artifact.stat().st_size > 10_000_000:
                        raise ValueError("output must be a regular JSON file within the size limit")
                    payload = artifact.read_text(encoding="utf-8")
                else:
                    saved = root / "executions" / result.get("execution_id", "") / "stdout.log"
                    payload = saved.read_text(encoding="utf-8") if saved.is_file() else result.get("stdout", "")
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError as exc:
                    raise ValueError(f'CLI output is not valid JSON (line {exc.lineno}, column {exc.colno}); '
                                     'keep logs on stderr, select the correct JSON output file, and check for HTML/login/error responses') from exc
                if expected_status in {'empty', 'invalid_input'}:
                    if (not isinstance(data, dict) or data.get('status') != expected_status
                            or data.get('records') != []):
                        raise ValueError(f'expected status={expected_status} and records=[]')
                    continue
                if (example.get('capability_id') or 'expected_status' in example) and (not isinstance(data, dict) or data.get('status') != 'ok'):
                    raise ValueError('capability success example must return status=ok')
                records = data[example["records_key"]] if example.get("records_key") else data
                if not isinstance(records, list) or not records:
                    raise ValueError("example must return a nonempty records array")
                for record in records:
                    if not isinstance(record, dict):
                        raise ValueError("each record must be an object")
                    requires_source = 'source_url' in example.get('required_fields', [])
                    source = record.get('source_url') if requires_source else record.get('url') or record.get('source_url')
                    if not _http_source_url(source):
                        raise ValueError('each record must retain a valid HTTP source_url' if requires_source
                                         else 'each record must retain a valid HTTP source URL')
                    # 必需的是输出字段；来源缺失值允许保留 null 或原始空值。
                    missing = [field for field in example.get('required_fields', []) if field not in record]
                    if missing:
                        raise ValueError('capability required fields missing: ' + ', '.join(missing))
            except Exception as exc:
                report = {"valid": False, "stage": "examples", "example": index, "argv": example.get("argv"),
                          "proxy_mode": example.get('proxy_mode', 'inherit'), "error": str(exc)[:4000]}
                if example.get('capability_id'):
                    report['capability_id'] = example['capability_id']
                    report['check_kind'] = example.get('check_kind', 'positive')
                if 'expected_status' in example:
                    report['expected_status'] = example['expected_status']
                if execution is not None:
                    # 非零退出常把结构化错误写在 stdout；仅有 failed 无法定位原因。
                    report['execution'] = _execution_feedback(execution)
                return report
    return {"valid": True, "stage": "complete", "examples": len(examples)}
