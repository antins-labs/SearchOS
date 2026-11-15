"""候选包文件、只读快照和文件工具；不调度 Agent 或修改验收状态。"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read a UTF-8 package file, a saved output path returned by a tool, "
            "or a file in the execution work_dir. Copy read_file arguments from next_actions when provided. "
            "Returns content, total_chars, truncated and next_offset. Follow next_offset to continue. "
            "The encoded response is capped at 24000 UTF-8 bytes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Package-relative path such as scripts/access.py, or the returned absolute path for a saved result."},
                "offset": {"type": "integer", "default": 0, "description": "Zero-based Unicode character offset. Use next_offset from the previous window."},
                "limit": {"type": "integer", "default": 16000, "minimum": 1, "maximum": 24000,
                          "description": "Maximum Unicode characters in this window, default 16000 and capped at 24000."},
            },
            "required": ["path"],
        },
    },
}


def _tool(name, description, properties, required=()):
    return {'type': 'function', 'function': {'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': properties,
                       'required': list(required), 'additionalProperties': False}}}


WRITE_FILE_TOOL = _tool('write_file', '创建或覆盖候选技能包中的 UTF-8 文件，返回路径和字符数。', {
    'path': {'type': 'string', 'description': '包内相对路径，例如 SKILL.md 或 scripts/access.py。'},
    'content': {'type': 'string', 'description': '要保存的完整文件正文。'}}, ['path', 'content'])
EDIT_FILE_TOOL = _tool('edit_file', '替换候选技能包文件中的精确文本，返回修改后的路径和字符数。', {
    'path': {'type': 'string', 'description': '已有包文件的相对路径。'},
    'old_text': {'type': 'string', 'description': '要匹配的非空原文，默认必须恰好出现一次。'},
    'new_text': {'type': 'string', 'description': '替换文本，空字符串表示删除匹配原文。'},
    'replace_all': {'type': 'boolean', 'default': False, 'description': '需要替换全部匹配时显式设为 true。'}},
    ['path', 'old_text', 'new_text'])


class PackageFiles:
    def __init__(self, output_dir, *, expected_name=None, runtime_dir, result_store, on_change):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.expected_name = expected_name or self.output_dir.name
        self.runtime_dir, self.result_store = Path(runtime_dir), result_store
        self.on_change = on_change
        self.files, self.read_roots = set(), set()
        self.update_base = None

    @contextmanager
    def snapshot(self):
        with tempfile.TemporaryDirectory(prefix='.access-validation-', dir=self.output_dir.parent) as temp:
            candidate = Path(temp) / self.expected_name
            self.copy_candidate(candidate)
            self.read_roots.add(candidate.resolve())
            try:
                yield candidate
            finally:
                self.read_roots.discard(candidate.resolve())

    def package_state(self):
        return {name: hashlib.sha256(self._resolve_inside(name).read_bytes()).hexdigest()
                for name in sorted(self.files)}


    def revision_error(self):
        if self.update_base is not None and self.package_state() == self.update_base:
            return {'valid': False, 'package_valid': False, 'stage': 'revision',
                    'error': 'update_has_no_changes: 请落实本次更新要求后提交验收。'}
        return None


    def copy_candidate(self, candidate):
        candidate.mkdir(parents=True, exist_ok=True)
        for relative in sorted(self.files):
            source = self._resolve_inside(relative)
            if source.is_symlink() or not source.is_file():
                raise ValueError('candidate files must be regular files')
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


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
        self.on_change()
        return {"path": str(target), "size": len(content)}


    async def read_file(self, path: str, offset: int = 0, limit: int = 16000) -> dict[str, Any]:
        import os
        import stat

        requested = Path(path)
        if '..' in requested.parts:
            raise ValueError('read_file path must not contain parent traversal')
        requested = requested if requested.is_absolute() else self.output_dir / requested
        runtime_dir = self.runtime_dir.absolute()
        runtime = runtime_dir.resolve()
        work_roots = {runtime_dir / 'work', runtime_dir / 'planner/work'}
        roots = [self.output_dir, self.result_store.root, *work_roots, *self.read_roots]
        target = None
        for root in roots:
            root = Path(root).absolute()
            if root.is_symlink():
                continue
            resolved_root = root.resolve()
            if root in work_roots and not resolved_root.is_relative_to(runtime):
                continue
            for alias in {root, resolved_root}:
                if not requested.is_relative_to(alias):
                    continue
                current = alias
                for part in requested.relative_to(alias).parts:
                    current = current / part
                    if current.is_symlink():
                        raise ValueError('read_file does not follow symbolic links')
                resolved = requested.resolve()
                if not resolved.is_relative_to(resolved_root):
                    raise ValueError('read_file path escapes an allowed directory')
                target = resolved
                break
            if target is not None:
                break
        if target is None:
            raise ValueError('read_file path must stay in the candidate, tool results or execution work directories')
        if not target.exists():
            return {"error": f"file not found: {path}", "path": str(target)}
        if not target.is_file():
            raise ValueError('read_file requires a regular text file')
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'r', encoding='utf-8') as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError('read_file requires a regular text file')
            return self.result_store.read_text_file(handle, path=target, offset=offset, limit=limit)


    async def read_candidate(self, candidate_dir, *, work_dir=None, **args):
        """Validator 仅读取当前固定候选、输出存储和本轮工作目录。"""
        path = Path(args["path"])
        if not path.is_absolute() and path.parts and path.parts[0] == "SKILL_DIR":
            path = Path(*path.parts[1:])
        if not path.is_absolute():
            if ".." in path.parts:
                raise ValueError("read_file path must stay in the candidate snapshot")
            path = candidate_dir / path
        roots = [candidate_dir, self.result_store.root]
        if work_dir is not None:
            roots.append(work_dir)
        if not any(path.resolve().is_relative_to(Path(root).resolve()) for root in roots):
            raise ValueError("validator reads only its candidate snapshot, saved results and validation work directory")
        return await self.read_file(**{**args, "path": str(path)})

    async def edit_file(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> dict:
        text = self._resolve_inside(path).read_text(encoding='utf-8')
        count = text.count(old_text) if old_text else 0
        if count == 0 or (count > 1 and not replace_all):
            raise ValueError('old_text must match exactly once; use replace_all only for deliberate global edits')
        return await self.write_file(path, text.replace(old_text, new_text))


    def _resolve_inside(self, path: str) -> Path:
        target = (self.output_dir / path).resolve()
        try:
            target.relative_to(self.output_dir)
        except ValueError as exc:
            raise ValueError(f"path escapes skill directory: {path}") from exc
        return target
