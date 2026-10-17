"""技能存储与资源文件路径；旧会话沿用原目录以保留绑定与执行回执。"""

from pathlib import Path


_COMPONENTS = ("packages", "bindings", "calls", "executions", "work")


def skill_workspace_dir(root: Path, component: str) -> Path:
    """新会话收拢到 skills/；整个旧会话统一沿用 skill_* 布局。"""
    if component not in _COMPONENTS:
        raise ValueError(f"Unknown skill workspace component: {component}")
    if any((root / f"skill_{name}").is_dir() for name in _COMPONENTS):
        return root / f"skill_{component}"
    return root / "skills" / component


def resolve_resource_file(root: Path, relative: str) -> Path:
    """解析技能包或执行快照内的普通文件，拒绝越界和符号链接。"""
    if not relative or Path(relative).is_absolute():
        raise ValueError("expected a relative file path")
    candidate = root / relative
    if any(part == ".." for part in Path(relative).parts):
        raise ValueError("parent traversal is not allowed")
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symbolic links are not readable skill resources")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("path escapes the resource directory")
    if not candidate.is_file():
        raise ValueError(f"file not found: {relative}")
    return candidate
