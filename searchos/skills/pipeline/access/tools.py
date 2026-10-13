"""Access Builder 工具：探索、包文件、CLI 调试与校验反馈。"""
from __future__ import annotations
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from searchos.skills.pipeline.access.valid import validate_access_package
from searchos.skills.pipeline.access.browser import ResearchBrowser, TOOL_DEFINITIONS as BROWSER_TOOLS

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
                    "Run Python code from the skill output directory. Use this "
                    "for site HTTP or Playwright browser probes and "
                    "site exploration. Playwright's fixed driver is "
                    "allowed; arbitrary subprocesses are blocked."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "timeout": {"type": "number", "default": 120},
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
                "description": "Read a UTF-8 text file under the skill directory.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "offset": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 7000}},
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
         "description": "Run a package CLI script in an isolated persistent work directory; use argv, not shell strings.",
         "parameters": {"type": "object", "properties": {
             "argv": {"type": "array", "items": {"type": "string"}},
             "stdin": {"type": "string"}, "timeout_s": {"type": "number"}}, "required": ["argv"]}}},
        {"type": "function", "function": {"name": "validate_skill",
         "description": "Validate the distributable SKILL.md + scripts package and execute registered real-data examples.",
         "parameters": {"type": "object", "properties": {}}}},
    ])

    def __init__(self, output_dir: Path, expected_name: str | None = None) -> None:
        self.output_dir = output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.expected_name = expected_name or output_dir.name
        self.require_host = True
        self.examples: list[dict[str, Any]] = []
        self.files: set[str] = set()
        self._runtime = tempfile.TemporaryDirectory(prefix="searchos-builder-runtime-")
        self.browser = ResearchBrowser()

    def close(self) -> None:
        self._runtime.cleanup()

    async def exec(self, argv: list[str], stdin: str = "", timeout_s: float = 60) -> dict:
        from searchos.skills.runtime.command_runtime import run_command
        root = Path(self._runtime.name)
        return await run_command(self.output_dir, argv, work_dir=root / "work",
                                 execution_dir=root / "executions", stdin=stdin,
                                 timeout_s=min(120, max(.1, timeout_s)), network=True)

    async def validate(self) -> dict:
        with tempfile.TemporaryDirectory(prefix=".builder-package-", dir=self.output_dir.parent) as tmp:
            candidate = Path(tmp) / self.expected_name
            candidate.mkdir()
            for relative in sorted(self.files):
                source = self._resolve_inside(relative)
                target = candidate / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            report = await validate_access_package(candidate, self.expected_name, self.examples, require_host=self.require_host)
            return report

    async def run_python(self, code: str, timeout: float = 120.0) -> dict[str, Any]:
        from searchos.skills.runtime.legacy.executor_runtime import (
            ExecutionPolicy,
            run_python_probe,
        )

        selected_timeout = max(1.0, float(timeout or 120.0))
        policy = ExecutionPolicy.access(
            timeout_s=selected_timeout,
            cpu_time_s=max(2, int(selected_timeout) + 1),
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
        return {"path": str(target), "size": len(content)}

    async def read_file(self, path: str, offset: int = 0, limit: int = 7000) -> dict[str, Any]:
        target = self._resolve_inside(path)
        if not target.exists():
            return {"error": f"file not found: {path}"}
        text = target.read_text(encoding="utf-8")
        start, count = max(0, offset), min(7000, max(1, limit))
        return {"content": text[start:start + count],
                "next_offset": start + count if start + count < len(text) else None}

    async def edit_file(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> dict:
        text = self._resolve_inside(path).read_text(encoding='utf-8')
        count = text.count(old_text) if old_text else 0
        if count == 0 or (count > 1 and not replace_all):
            raise ValueError('old_text must match exactly once; use replace_all only for deliberate global edits')
        return await self.write_file(path, text.replace(old_text, new_text))

    async def dispatch(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        if tool_name in {"web_search", "web_open", "web_find"}:
            return await self.browser.dispatch(tool_name, tool_input)
        if tool_name == "register_example":
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
            replacement = tool_input.get("replace_index")
            if replacement is not None:
                if not isinstance(replacement, int) or not 0 <= replacement < len(self.examples):
                    raise ValueError("replace_index must identify a registered example")
                self.examples[replacement] = example
            elif example not in self.examples:
                self.examples.append(example)
            return {"registered": len(self.examples)}
        if tool_name == "exec":
            return await self.exec(tool_input["argv"], str(tool_input.get("stdin", "")), float(tool_input.get("timeout_s", 60)))
        if tool_name == "validate_skill":
            return await self.validate()
        if tool_name == "run_python":
            return await self.run_python(
                str(tool_input["code"]),
                timeout=float(tool_input.get("timeout") or 120.0),
            )
        if tool_name == "write_file":
            return await self.write_file(str(tool_input["path"]), str(tool_input["content"]))
        if tool_name == "read_file":
            return await self.read_file(str(tool_input["path"]), int(tool_input.get('offset', 0)), int(tool_input.get('limit', 7000)))
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
        payload = json.dumps(result, ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
    if len(payload) > 10000:
        payload = json.dumps({'truncated': True, 'content': payload[:9000]}, ensure_ascii=False)
    return ToolMessage(
        content=payload,
        tool_call_id=call_id or "missing-tool-call-id",
        name=name or None,
    )

