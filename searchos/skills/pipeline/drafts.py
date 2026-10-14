"""未通过验证的候选包检查点；独立存储，不能被技能目录发现。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4


def package_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('draft file must stay inside the package')
    if value not in {'SKILL.md', 'requirements.txt', 'package.json', 'package-lock.json'} and path.parts[0] not in {'scripts', 'references', 'assets'}:
        raise ValueError('unsupported draft package file')
    return path


def save_draft(root: Path, source: Path, files, *, name: str, examples: list, require_host: bool,
               validation: dict | None = None) -> Path | None:
    if not files:
        return None
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    revision = root / 'drafts' / uuid4().hex
    package = revision / name
    package.mkdir(parents=True, mode=0o700)
    manifest = {}
    try:
        for value in sorted(files):
            relative = package_path(str(value))
            original = source / relative
            if original.is_symlink() or not original.resolve().is_relative_to(source.resolve()):
                raise ValueError('draft file escapes source package')
            target = package / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            target.chmod(0o600)
            manifest[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest()
        data = dict(version=1, name=name, package=str(package.relative_to(root)), files=manifest,
                    examples=examples, require_host=require_host, validation=validation or {})
        pointer = root / 'draft.json'
        temporary = root / 'draft.tmp'
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        temporary.chmod(0o600)
        temporary.replace(pointer)
        return pointer
    except BaseException:
        shutil.rmtree(revision, ignore_errors=True)
        raise


def load_draft(pointer: Path) -> tuple[Path, dict]:
    if pointer.is_symlink():
        raise ValueError('draft pointer must not be a symlink')
    data = json.loads(pointer.read_text())
    if data.get('version') != 1:
        raise ValueError('unsupported draft version')
    relative = Path(data['package'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('invalid draft package path')
    root = pointer.parent.resolve()
    package = root / relative
    if package.is_symlink() or not package.resolve().is_relative_to(root):
        raise ValueError('draft package escapes record directory')
    for value, digest in data['files'].items():
        p = package / package_path(value)
        if p.is_symlink() or not p.resolve().is_relative_to(package.resolve()):
            raise ValueError('draft file escapes package')
        if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise ValueError(f'draft file hash mismatch: {value}')
    return package, data
