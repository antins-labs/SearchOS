"""Access 包结构与真实 CLI 样例校验，不在主进程导入生成代码。"""
from __future__ import annotations
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
        if (output_dir / "manifest.yaml").exists() or (output_dir / "executor.py").exists():
            return False
        scripts = [p for p in (output_dir / "scripts").rglob("*") if p.is_file()]
        if not any(p.suffix in {".py", ".sh", ".js", ".mjs", ".cjs"} for p in scripts):
            return False
        import ast
        for script in scripts:
            if script.suffix != ".py":
                continue
            tree = ast.parse(script.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                imports = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                if any(name == "searchos" or name.startswith("searchos.") for name in imports):
                    return False
        return True
    except (ValueError, OSError, SyntaxError, yaml.YAMLError):
        logger.warning("invalid portable package: %s", output_dir, exc_info=True)
        return False


def transport_policy(package: Path) -> dict:
    """筛出已观察到的显式 TLS 降级写法，不把静态扫描当作完整保证。"""
    import ast
    findings = []
    for path in sorted((package / 'scripts').rglob('*.py')):
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except (OSError, SyntaxError):
            findings.append({'file': str(path.relative_to(package)), 'marker': 'unreadable_python'})
            continue
        for node in ast.walk(tree):
            marker = None
            if isinstance(node, ast.Assign):
                attrs = {target.attr for target in node.targets if isinstance(target, ast.Attribute)}
                if 'check_hostname' in attrs and isinstance(node.value, ast.Constant) and node.value.value is False:
                    marker = 'check_hostname_false'
                if 'verify_mode' in attrs and isinstance(node.value, ast.Attribute) and node.value.attr == 'CERT_NONE':
                    marker = 'certificate_verification_disabled'
            if isinstance(node, ast.Call):
                if any(k.arg == 'verify' and isinstance(k.value, ast.Constant) and k.value.value is False for k in node.keywords):
                    marker = 'verify_false'
                if any(k.arg == 'ignore_https_errors' and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
                    marker = 'browser_ignores_https_errors'
                if isinstance(node.func, ast.Attribute) and node.func.attr == '_create_unverified_context':
                    marker = 'unverified_ssl_context'
            if marker:
                findings.append({'file': str(path.relative_to(package)), 'line': node.lineno, 'marker': marker})
    return {'kind': 'transport_policy', 'passed': not findings, 'findings': findings,
            'scope': '显式 TLS 降级模式检查；不覆盖所有别名、动态行为或其他安全属性。'}


async def validate_access_package(output_dir: Path, expected_name: str, examples: list[dict], *, require_host: bool = True) -> dict:
    from searchos.skills.packaging import validate_package
    try:
        skill = validate_package(output_dir, expected_name=expected_name)
        if skill.meta.category.value != "access":
            raise ValueError("Access packages require metadata.searchos-category: access in SKILL.md frontmatter")
        frontmatter = (output_dir / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
        metadata = (yaml.safe_load(frontmatter) or {}).get("metadata", {})
        if not isinstance(metadata, dict) or (require_host and not str(metadata.get("host", "")).strip()):
            raise ValueError("Access packages require metadata.host in SKILL.md frontmatter")
        if not package_is_complete(output_dir, expected_name):
            raise ValueError("require SKILL.md + scripts/ without legacy executor or manifest")
        policy = transport_policy(output_dir)
        if not policy['passed']:
            return {'valid': False, 'stage': 'transport_policy',
                    'error': 'remove explicit TLS certificate-verification downgrades', **policy}
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


def _invalid_payload(value, *, allow_failure: bool = False) -> bool:
    if isinstance(value, dict):
        invalid = value.get('fixture') or value.get('input_mode') == 'fixture'
        if not allow_failure:
            invalid = invalid or value.get('error') or value.get('success') is False
        return bool(invalid) or any(_invalid_payload(v, allow_failure=allow_failure) for v in value.values())
    return isinstance(value, list) and any(_invalid_payload(v, allow_failure=allow_failure) for v in value)


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


def _empty_required_value(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or (
        isinstance(value, (list, dict)) and not value)


def _http_source_url(value) -> bool:
    from urllib.parse import urlparse
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        return False
    try:
        url = urlparse(value)
        return url.scheme in {'http', 'https'} and bool(url.hostname) and (url.port is None or url.port > 0)
    except ValueError:
        return False


async def _capability_failure_probes(output_dir: Path, examples: list[dict]) -> dict | None:
    """只验收宿主编译的站点 CLI；普通注册样例沿用原协议。"""
    from searchos.skills.runtime.command_runtime import run_command
    checked = set()
    for index, example in enumerate(examples):
        capability = example.get('capability_id')
        argv = example.get('argv', [])
        if (not capability or capability in checked or len(argv) != 5
                or example.get('expected_status', 'ok') != 'ok' or example.get('check_kind') == 'boundary'
                or argv[:4] != ['python', 'scripts/access.py', capability, '--input']
                or example.get('output', '') or example.get('records_key') != 'records'):
            continue
        checked.add(capability)
        probes = [('invalid_input', [*argv[:4], 'null']),
                  ('invalid_input', [*argv[:4], '[]']), ('network_denied', argv)]
        for kind, probe_argv in probes:
            with tempfile.TemporaryDirectory(prefix='searchos-build-failure-probe-') as temporary:
                root = Path(temporary)
                execution = None
                try:
                    execution = await run_command(output_dir, probe_argv, work_dir=root / 'work',
                        execution_dir=root / 'executions', timeout_s=15, network=False)
                    if (execution.get('exit_code') in (None, 0) or execution.get('timed_out')
                            or execution.get('started') is False
                            or execution.get('status') in {'blocked', 'cancelled', 'timed_out'}):
                        raise ValueError('probe requires a completed CLI failure with a nonzero exit code')
                    saved = root / 'executions' / execution.get('execution_id', '') / 'stdout.log'
                    payload = saved.read_text(encoding='utf-8') if saved.is_file() else execution.get('stdout', '')
                    data = json.loads(payload)
                    if _invalid_payload(data, allow_failure=True):
                        raise ValueError('failure probe contains fixture data')
                    if (not isinstance(data, dict) or data.get('records') != []
                            or not isinstance(data.get('warnings'), list)
                            or not all(isinstance(warning, str) for warning in data['warnings'])):
                        raise ValueError('failure JSON requires records=[] and warnings as an array of strings')
                    status = data.get('status')
                    if kind == 'invalid_input':
                        if status != 'invalid_input':
                            raise ValueError('non-object JSON input must return status=invalid_input')
                    elif not isinstance(status, str) or not status.strip() or status in {'ok', 'empty', 'invalid_input'}:
                        raise ValueError('network-denied valid input must return an explicit access failure status')
                except Exception as exc:
                    report = {'valid': False, 'stage': 'examples', 'example': index,
                              'capability_id': capability, 'check_kind': kind, 'argv': probe_argv,
                              'error': f'{kind} probe failed: {exc}'[:4000]}
                    if execution is not None:
                        report['error'] = (report['error'] + '; ' + _failure_reason(execution))[:4000]
                        report['execution'] = _execution_feedback(execution)
                    return report
    return None


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
                    if _invalid_payload(data, allow_failure=expected_status == 'invalid_input'):
                        raise ValueError('boundary example contains fixture data or an unexpected failure result')
                    if (not isinstance(data, dict) or data.get('status') != expected_status
                            or data.get('records') != [] or not isinstance(data.get('warnings'), list)
                            or not all(isinstance(warning, str) for warning in data['warnings'])):
                        raise ValueError(f'expected status={expected_status}, records=[] and warnings as an array of strings')
                    continue
                if _invalid_payload(data):
                    raise ValueError("example contains fixture data or a failure result")
                if (example.get('capability_id') or 'expected_status' in example) and (not isinstance(data, dict) or data.get('status') != 'ok'):
                    raise ValueError('capability success example must return status=ok')
                records = data[example["records_key"]] if example.get("records_key") else data
                if not isinstance(records, list) or not records:
                    raise ValueError("example must return a nonempty records array")
                for record in records:
                    if not isinstance(record, dict) or len(record) < 2:
                        raise ValueError("each record must contain data and a source URL")
                    requires_source = 'source_url' in example.get('required_fields', [])
                    source = record.get('source_url') if requires_source else record.get('url') or record.get('source_url')
                    if not _http_source_url(source):
                        raise ValueError('each record must retain a valid HTTP source_url' if requires_source
                                         else 'each record must retain a valid HTTP source URL')
                    missing = [field for field in example.get('required_fields', [])
                               if field not in record or _empty_required_value(record[field])]
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
    if failure := await _capability_failure_probes(output_dir, examples):
        return failure
    return {"valid": True, "stage": "complete", "examples": len(examples)}
