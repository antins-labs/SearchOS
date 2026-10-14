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


def _invalid_payload(value) -> bool:
    if isinstance(value, dict):
        return bool(value.get("fixture") or value.get("input_mode") == "fixture" or value.get("error") or value.get("success") is False) or any(_invalid_payload(v) for v in value.values())
    return isinstance(value, list) and any(_invalid_payload(v) for v in value)


async def validate_examples(output_dir: Path, examples: list[dict[str, Any]]) -> dict:
    from urllib.parse import urlparse
    from searchos.skills.runtime.command_runtime import run_command
    if not examples:
        return {"valid": False, "stage": "examples", "error": "register at least one complete real-data CLI example"}
    checked_entries = set()
    for index, example in enumerate(examples):
        with tempfile.TemporaryDirectory(prefix="searchos-build-validation-") as temporary:
            root = Path(temporary)
            work = root / "work"
            work.mkdir()
            try:
                entry = tuple(example["argv"][:2])
                if entry not in checked_entries:
                    help_result = await run_command(output_dir, [*entry, "--help"], work_dir=root / "help-work",
                        execution_dir=root / "help-executions", timeout_s=15, network=False)
                    if help_result.get("exit_code") != 0 or help_result.get("error"):
                        raise ValueError("CLI --help failed: " + str(help_result.get("error") or help_result.get("stderr", "")))
                    checked_entries.add(entry)
                result = await run_command(output_dir, example["argv"], work_dir=work,
                    execution_dir=root / "executions", timeout_s=60, network=True,
                    proxy_mode=example.get('proxy_mode', 'inherit'))
                if result.get('auth_required'):
                    return {'valid': False, 'stage': 'authentication', 'auth_required': True,
                            'example': index, 'argv': example['argv'], 'proxy_mode': example.get('proxy_mode', 'inherit'),
                            'error': result.get('error', 'auth_required')}
                if result.get("exit_code") != 0 or result.get("error") or result.get("timed_out") or result.get("status", "completed") != "completed":
                    raise ValueError(f"command failed: {result.get('error') or result.get('stderr') or result.get('status')}")
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
                if _invalid_payload(data):
                    raise ValueError("example contains fixture data or a failure result")
                records = data[example["records_key"]] if example.get("records_key") else data
                if not isinstance(records, list) or not records:
                    raise ValueError("example must return a nonempty records array")
                for record in records:
                    if not isinstance(record, dict) or len(record) < 2:
                        raise ValueError("each record must contain data and a source URL")
                    url = urlparse(str(record.get("url") or record.get("source_url") or ""))
                    if url.scheme not in {"http", "https"} or not url.hostname:
                        raise ValueError("each record must retain a valid HTTP source URL")
            except Exception as exc:
                return {"valid": False, "stage": "examples", "example": index, "argv": example.get("argv"),
                        "proxy_mode": example.get('proxy_mode', 'inherit'), "error": str(exc)[:4000]}
    return {"valid": True, "stage": "complete", "examples": len(examples)}
