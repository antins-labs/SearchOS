"""Portable package validation, deterministic snapshots, and atomic installation.

No archive extraction or code execution takes place in this module.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

_EXCLUDED_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "venv", ".cache", "runs", "logs"}
_EXCLUDED_FILES = {".env", "credentials", "credentials.json", "secrets.json", "execution.json", ".DS_Store"}


def package_files(skill_dir: str | Path) -> list[Path]:
    """Return distributable relative paths; reject links even in excluded trees."""
    root = Path(skill_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Package must be a real directory: {root}")
    result = []
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            p = Path(base) / name
            if p.is_symlink():
                raise ValueError(f"Symlinks are not allowed in packages: {p}")
        # Inspect all trees for links, including excluded directories.
        dirs[:] = sorted(dirs)
        excluded_tree = any(part in _EXCLUDED_DIRS or part.startswith('.') for part in Path(base).relative_to(root).parts)
        if excluded_tree:
            continue
        for name in sorted(files):
            p = Path(base) / name
            if name in _EXCLUDED_FILES or name.startswith('.env') or name.endswith(('.pyc', '.pyo', '.pem', '.key', '.log')):
                continue
            if not p.is_file():
                raise ValueError(f"Not a regular package file: {p}")
            result.append(p.relative_to(root))
    return sorted(result)


def package_fingerprint(skill_dir: str | Path) -> str:
    root = Path(skill_dir)
    digest = hashlib.sha256()
    for relative in package_files(root):
        data = (root / relative).read_bytes()
        digest.update(relative.as_posix().encode() + b'\0')
        digest.update(str((root / relative).stat().st_mode & 0o111).encode() + b'\0')
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def snapshot_package(skill_dir: str | Path, destination: str | Path) -> Path:
    """Copy allowed files atomically to a new directory, never overwrite."""
    root, dest = Path(skill_dir).resolve(), Path(destination)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(dest)
    if Path(skill_dir).is_symlink():
        raise ValueError("Symlink package root")
    if dest.resolve().is_relative_to(root):
        raise ValueError("Destination cannot be inside the source package")
    files = package_files(root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if any(p.is_symlink() for p in [dest.parent, *dest.parent.parents]):
        raise ValueError("Destination parent cannot be a symlink")
    staging = Path(tempfile.mkdtemp(prefix='.skill-stage-', dir=dest.parent))
    try:
        for relative in files:
            src = root / relative
            if src.is_symlink() or not src.resolve().is_relative_to(root):
                raise ValueError(f"Package path escaped: {relative}")
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        if dest.exists():
            raise FileExistsError(dest)
        staging.rename(dest)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return dest


def validate_package(skill_dir: str | Path, *, expected_name: str | None = None):
    """Validate a standard package and return its parsed Skill."""
    from searchos.skills.core.schema import parse_skill_file, find_skill_entry
    root = Path(skill_dir)
    package_files(root)
    entry = find_skill_entry(root)
    if entry.name != 'SKILL.md':
        raise ValueError('Portable packages require SKILL.md; legacy packages must be migrated')
    return parse_skill_file(entry, expected_name=expected_name)


def install_package(skill_dir: str | Path, library_dir: str | Path) -> Path:
    skill = validate_package(skill_dir)
    return snapshot_package(skill_dir, Path(library_dir) / skill.meta.name)


def export_package(skill_dir: str | Path, destination: str | Path) -> Path:
    skill = validate_package(skill_dir)
    dest = Path(destination)
    if dest.name != skill.meta.name:
        raise ValueError('Export directory must match the skill name')
    return snapshot_package(skill_dir, dest)
