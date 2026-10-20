"""Access Builder 工具：探索、包文件、CLI 调试与校验反馈。"""
from __future__ import annotations
import json
from copy import deepcopy
import shutil
import tempfile
from pathlib import Path
from typing import Any

from searchos.skills.pipeline.access.valid import validate_access_package
from searchos.skills.pipeline.access.browser import ResearchBrowser, TOOL_DEFINITIONS as BROWSER_TOOLS
from searchos.skills.runtime.network import PROXY_SCHEMA, validate_proxy_mode

class BuilderWorkspace:
    """受 Skill Execution 策略约束的构建工作区。"""

    # OpenAI Chat Completions tool format (the builder runs against any
    # OpenAI-compatible endpoint).
    TOOL_DEFINITIONS = [
        {
            "type": "function",
            "function": {
                "name": "run_python",
                "description": (
                    "Probe HTTP or Playwright from the skill output directory in a "
                    "restricted Python worker. For Scrapy, native dependencies or a "
                    "complete browser workflow, write the package CLI and use exec "
                    "to test it in the final execution environment."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "timeout": {"type": "number", "default": 120},
                        "proxy_mode": PROXY_SCHEMA,
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": (
                    "Write a UTF-8 text file under the skill directory. Use "
                    "paths like SKILL.md, scripts/search.py, or references/api.md."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a UTF-8 text file under the skill directory. offset and limit count characters, not lines. Default limit is 16000; maximum is 24000. Returns content, total_chars, truncated and next_offset; follow next_offset when truncated.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "offset": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 16000, "minimum": 1, "maximum": 24000}},
                    "required": ["path"],
                },
            },
        },
    ]

    TOOL_DEFINITIONS.append({
        "type": "function",
        "function": {
            "name": "register_example",
            "description": "Register a complete real-data CLI example for installation validation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "argv": {"type": "array", "items": {"type": "string"}},
                    "output": {"type": "string"},
                    "records_key": {"type": "string"},
                    "proxy_mode": PROXY_SCHEMA,
                    "replace_index": {"type": "integer", "description": "Replace a previously registered example when repairing its arguments."},
                },
                "required": ["argv", "output", "records_key"],
            },
        },
    })

    TOOL_DEFINITIONS.extend([
        {"type": "function", "function": {"name": "edit_file",
         "description": "Replace exact text in an existing package file. Reject ambiguous matches unless replace_all is true; prefer this for small repairs.",
         "parameters": {"type": "object", "properties": {
             "path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"},
             "replace_all": {"type": "boolean", "default": False}}, "required": ["path", "old_text", "new_text"]}}},
        {"type": "function", "function": {"name": "exec",
         "description": "Run a package CLI in the final isolated runtime, including installed Scrapy/Playwright libraries. Use argv and write outputs to the persistent work directory. Dependency declarations do not install libraries.",
         "parameters": {"type": "object", "properties": {
             "argv": {"type": "array", "items": {"type": "string"}},
             "stdin": {"type": "string"}, "timeout_s": {"type": "number"},
             "proxy_mode": PROXY_SCHEMA}, "required": ["argv"]}}},
        {"type": "function", "function": {"name": "validate_skill",
         "description": "Execute the declared capability examples and check their CLI output. Repair reported errors and validate again.",
         "parameters": {"type": "object", "properties": {}}}},
    ])

    def __init__(self, output_dir: Path, expected_name: str | None = None) -> None:
        self.output_dir = output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.expected_name = expected_name or output_dir.name
        self.require_host = True
        self.expected_host: str | None = None
        self.last_validation: dict = {}
        self.checked_state = None
        self.update_base = None
        self.checkpoint = lambda: None
        self.examples: list[dict[str, Any]] = []
        self.examples_locked = False
        self.files: set[str] = set()
        self._runtime = tempfile.TemporaryDirectory(prefix="searchos-builder-runtime-")
        self.browser = ResearchBrowser()
        self.site_intent = None

    def set_validation_examples(self, examples: list[dict]) -> None:
        """接收宿主编译的验收样例；模型只能修实现，不能改验收目标。"""
        if not isinstance(examples, list) or not examples:
            raise ValueError('host validation examples must be a nonempty list')
        for example in examples:
            if not isinstance(example, dict):
                raise ValueError('host validation example must be an object')
            argv = example.get('argv')
            if (not isinstance(argv, list) or len(argv) < 2
                    or not all(isinstance(v, str) for v in argv)):
                raise ValueError('host example argv must contain an interpreter and a script')
            script = Path(argv[1])
            if not script.parts or script.is_absolute() or '..' in script.parts or script.parts[0] != 'scripts':
                raise ValueError('host example entry must stay under scripts/')
            output = example.get('output', '')
            if not isinstance(output, str) or (output and (Path(output).is_absolute() or '..' in Path(output).parts)):
                raise ValueError('host example output must stay in the working directory')
            if not isinstance(example.get('records_key', ''), str):
                raise ValueError('host example records_key must be a string')
            if example.get('expected_status', 'ok') not in ('ok', 'empty', 'invalid_input'):
                raise ValueError('host example expected_status must be ok, empty or invalid_input')
            if 'proxy_mode' in example:
                validate_proxy_mode(example['proxy_mode'])
        self.examples = deepcopy(examples)
        self.examples_locked = True

    def close(self) -> None:
        self._runtime.cleanup()

    async def exec(self, argv: list[str], stdin: str = "", timeout_s: float = 60, proxy_mode: str = 'inherit') -> dict:
        from searchos.skills.runtime.command_runtime import run_command
        root = Path(self._runtime.name)
        return await run_command(self.output_dir, argv, work_dir=root / "work",
                                 execution_dir=root / "executions", stdin=stdin,
                                 timeout_s=min(120, max(.1, timeout_s)), network=True, proxy_mode=proxy_mode)

    def package_state(self):
        import hashlib
        return {name: hashlib.sha256(self._resolve_inside(name).read_bytes()).hexdigest()
                for name in sorted(self.files)}

    def revision_error(self):
        if self.update_base is not None and self.package_state() == self.update_base:
            return {'valid': False, 'stage': 'revision',
                    'error': 'update_has_no_changes: 旧包通过基础样例不表示本次修复完成；请先落实请求中的文件修改。'}
        return None

    def validation_state(self):
        return self.package_state(), deepcopy(self.examples), self.require_host, self.expected_host

    async def validate(self) -> dict:
        self.checked_state = None
        state = self.validation_state()
        if error := self.revision_error():
            self.last_validation = error
            self.checked_state = state
            self.checkpoint()
            return error
        with tempfile.TemporaryDirectory(prefix=".builder-package-", dir=self.output_dir.parent) as tmp:
            candidate = Path(tmp) / self.expected_name
            candidate.mkdir()
            for relative in sorted(self.files):
                source = self._resolve_inside(relative)
                target = candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            report = await validate_access_package(candidate, self.expected_name, self.examples,
                                                   require_host=self.require_host,
                                                   expected_host=self.expected_host)
            self.last_validation = report
            self.checked_state = state
            self.checkpoint()
            return report

    async def run_python(self, code: str, timeout: float = 120.0, proxy_mode: str = 'inherit') -> dict[str, Any]:
        from searchos.skills.runtime.legacy.executor_runtime import (
            ExecutionPolicy,
            run_python_probe,
        )

        selected_timeout = min(120.0, max(1.0, float(timeout or 120.0)))
        policy = ExecutionPolicy.access(
            timeout_s=selected_timeout,
            cpu_time_s=max(2, int(selected_timeout) + 1),
            proxy_mode=proxy_mode,
        )
        return await run_python_probe(code, self.output_dir, policy=policy)

    async def write_file(self, path: str, content: str) -> dict[str, Any]:
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("package file must use a relative path")
        if path not in {"SKILL.md", "requirements.txt", "package.json", "package-lock.json"} and (not relative.parts or relative.parts[0] not in {"scripts", "references", "assets"}):
            raise ValueError("write SKILL.md, dependency files, or files under scripts/references/assets")
        target = self._resolve_inside(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.files.add(relative.as_posix())
        self.checkpoint()
        return {"path": str(target), "size": len(content)}

    async def read_file(self, path: str, offset: int = 0, limit: int = 16000) -> dict[str, Any]:
        target = self._resolve_inside(path)
        if not target.exists():
            return {"error": f"file not found: {path}"}
        text = target.read_text(encoding="utf-8")
        start, count = max(0, offset), min(24000, max(1, limit))
        truncated = start + count < len(text)
        return {"content": text[start:start + count], "total_chars": len(text), "truncated": truncated,
                "next_offset": start + count if truncated else None}

    async def edit_file(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> dict:
        text = self._resolve_inside(path).read_text(encoding='utf-8')
        count = text.count(old_text) if old_text else 0
        if count == 0 or (count > 1 and not replace_all):
            raise ValueError('old_text must match exactly once; use replace_all only for deliberate global edits')
        return await self.write_file(path, text.replace(old_text, new_text))

    async def dispatch(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        if tool_name == 'ask_intent_agent' and self.site_intent is not None:
            return await self.site_intent.advise(**tool_input)
        if tool_name in {"web_search", "web_open", "web_find"}:
            return await self.browser.dispatch(tool_name, tool_input)
        if tool_name == "register_example":
            if self.examples_locked:
                return {'error': 'host_validation_examples_locked', 'registered': len(self.examples),
                        'next_action': '验收样例及预期状态已由宿主注册；无需重复注册或修改。请修复脚本，使用 exec 检查负例，使用 validate_skill 验收。'}
            argv = tool_input.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(v, str) for v in argv):
                raise ValueError("argv must be a nonempty string array")
            output = str(tool_input.get("output", ""))
            if output and (Path(output).is_absolute() or ".." in Path(output).parts):
                raise ValueError("example output must stay in the working directory")
            from searchos.skills.runtime.command_runtime import _entry
            _entry(self.output_dir, argv)
            if Path(argv[1]).parts[0] != "scripts":
                raise ValueError("example entry must be under scripts/")
            example = {"argv": argv, "output": output, "records_key": str(tool_input.get("records_key", ""))}
            if 'proxy_mode' in tool_input:
                example['proxy_mode'] = validate_proxy_mode(tool_input['proxy_mode'])
            replacement = tool_input.get("replace_index")
            if replacement is not None:
                if not isinstance(replacement, int) or not 0 <= replacement < len(self.examples):
                    raise ValueError("replace_index must identify a registered example")
                self.examples[replacement] = example
            elif example not in self.examples:
                self.examples.append(example)
            self.checkpoint()
            return {"registered": len(self.examples)}
        if tool_name == "exec":
            return await self.exec(tool_input["argv"], str(tool_input.get("stdin", "")), float(tool_input.get("timeout_s", 60)), tool_input.get('proxy_mode', 'inherit'))
        if tool_name == "validate_skill":
            return await self.validate()
        if tool_name == "run_python":
            return await self.run_python(
                str(tool_input["code"]),
                timeout=float(tool_input.get("timeout") or 120.0),
                proxy_mode=tool_input.get('proxy_mode', 'inherit'),
            )
        if tool_name == "write_file":
            return await self.write_file(str(tool_input["path"]), str(tool_input["content"]))
        if tool_name == "read_file":
            return await self.read_file(str(tool_input["path"]), int(tool_input.get('offset', 0)), int(tool_input.get('limit', 16000)))
        if tool_name == 'edit_file':
            return await self.edit_file(str(tool_input['path']), str(tool_input['old_text']), str(tool_input['new_text']), bool(tool_input.get('replace_all', False)))
        return {"error": f"unknown tool: {tool_name}"}

    def _resolve_inside(self, path: str) -> Path:
        target = (self.output_dir / path).resolve()
        try:
            target.relative_to(self.output_dir)
        except ValueError as exc:
            raise ValueError(f"path escapes skill directory: {path}") from exc
        return target

BuilderWorkspace.TOOL_DEFINITIONS.extend(BROWSER_TOOLS)


async def run_tool(workspace: BuilderWorkspace, tool_call: Any) -> Any:
    """Execute one normalized LangChain tool call and return a ToolMessage."""
    from langchain_core.messages import ToolMessage

    name = ""
    call_id = ""
    try:
        if not isinstance(tool_call, dict):
            raise TypeError("tool call must be a normalized mapping")
        name = str(tool_call.get("name", ""))
        call_id = str(tool_call.get("id", ""))
        args = tool_call.get("args") or {}
        if isinstance(args, str):
            args = json.loads(args or "{}")
        if not isinstance(args, dict):
            raise TypeError("tool call args must be an object")
        result = await workspace.dispatch(name, args)
        if workspace.site_intent is not None:
            observation = workspace.site_intent.observe(name, args, result, 'builder')
            if observation is not None:
                result = {**result, 'observation_id': observation}
        payload = json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
    # read_file 已按字符分页；二次截断会破坏 content 与 next_offset 的对应关系。
    if name != 'read_file' and len(payload) > 10000:
        payload = json.dumps({'truncated': True, 'content': payload[:9000]}, ensure_ascii=False)
    return ToolMessage(
        content=payload,
        tool_call_id=call_id or "missing-tool-call-id",
        name=name or None,
    )

